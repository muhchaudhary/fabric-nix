"""
What the desktop's media widgets show: which MPRIS player (switchable when
several are running), where it is in the track, and synced lyrics.

Players don't announce their position, so it's estimated: read once when
the track, playback status or player changes, then counted forward while
playing. Lyrics come from LRCLIB (lrclib.net, free, no key) and are cached.
"""

import hashlib
import json
import os
import re
import threading

from fabric.core.service import Service, Signal
from gi.repository import GLib
from loguru import logger

import fabric_config.config as config

LYRICS_CACHE = os.path.join(GLib.get_user_cache_dir(), "fabric", "lyrics")
LRCLIB = "https://lrclib.net/api"
USER_AGENT = "fabric-config (https://github.com/muhchaudhary/fabric-nix)"

# a paused selection gives way to another player that starts playing, but
# only once you haven't touched it for this long
AUTO_SWITCH_AFTER_S = 20

_LRC_LINE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")


def parse_lrc(text: str) -> list[tuple[float, str]]:
    """[(seconds, line)], sorted; a line may carry several timestamps."""
    lines = []
    for raw in text.splitlines():
        stamps = _LRC_LINE.findall(raw)
        lyric = _LRC_LINE.sub("", raw).strip()
        for minutes, seconds in stamps:
            lines.append((int(minutes) * 60 + float(seconds), lyric))
    return sorted(lines)


class MediaState(Service):
    @Signal
    def changed(self) -> None: ...

    @Signal
    def lyrics_changed(self) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # the player being shown and controlled (a bus name). It sticks:
        # following "whichever is playing" would hand the next click to a
        # different player as soon as you paused this one
        self._selected: str | None = None
        self._last_interaction = 0.0
        self._track_key: tuple | None = None
        self._status = "Stopped"
        self._pos_base = 0.0
        self._pos_time = 0.0
        self.lyrics: list[tuple[float, str]] = []
        self._lyrics_key: tuple | None = None

        manager = config.mprisplayer
        manager.connect("player-appeared", lambda _m, p: self._watch(p))
        manager.connect("player-vanished", lambda *_: self._on_change())
        for player in manager.players.values():
            self._watch(player)

    # Players

    def players(self) -> list:
        return sorted(config.mprisplayer.players.values(), key=lambda p: p.bus_name)

    def current_player(self):
        for player in self.players():
            if player.bus_name == self._selected:
                return player
        return None

    def _choose_player(self):
        """Keep the selection unless it's gone, or idle while another plays."""
        players = self.players()
        current = self.current_player()
        playing = [p for p in players if p.playback_status == "Playing"]
        now = GLib.get_monotonic_time() / 1e6
        if current is None:
            chosen = (playing or players or [None])[0]
        elif (
            current.playback_status != "Playing"
            and playing
            and now - self._last_interaction > AUTO_SWITCH_AFTER_S
        ):
            chosen = playing[0]
        else:
            return
        self._selected = chosen.bus_name if chosen else None

    def cycle_player(self, step: int):
        players = self.players()
        if len(players) < 2:
            return
        current = self.current_player()
        index = players.index(current) if current in players else 0
        self._selected = players[(index + step) % len(players)].bus_name
        self._last_interaction = GLib.get_monotonic_time() / 1e6
        self._on_change()

    def act(self, action: str):
        """Run a player method (play_pause, next, previous) on the shown player."""
        player = self.current_player()
        if player is None:
            return
        self._last_interaction = GLib.get_monotonic_time() / 1e6
        method = getattr(player, action, None)
        if callable(method):
            method()

    def _watch(self, player):
        player.connect("changed", lambda *_: self._on_change())
        player.connect("seeked", lambda p, *_: self._on_seeked(p))
        self._on_change()

    def _on_seeked(self, player):
        if player is self.current_player():
            self._resync(player, reset=False, reached=self.position)
            self.changed()

    def seek(self, fraction: float):
        """Jump to `fraction` (0-1) of the current track."""
        player = self.current_player()
        if player is None or not player.length or not player.can_seek:
            return
        target = int(max(0.0, min(1.0, fraction)) * player.length)
        self._last_interaction = GLib.get_monotonic_time() / 1e6
        # show the new position at once; Seeked (or the next read) confirms it
        self._pos_base, self._pos_time = float(target), self._last_interaction
        player.seek_to(target)
        self.changed()

    def _on_change(self):
        self._choose_player()
        player = self.current_player()
        key = (
            (player.bus_name, player.title, tuple(player.artist or []))
            if player
            else None
        )
        status = player.playback_status if player else "Stopped"
        if key != self._track_key or status != self._status:
            new_track = key != self._track_key
            reached = self.position  # before the status changes
            self._track_key, self._status = key, status
            self._resync(player, reset=new_track, reached=reached)
            if new_track:
                self._load_lyrics(player)
        self.changed()

    # Position

    def _resync(self, player, reset: bool, reached: float):
        # carry on from the estimate until the player reports its position
        self._pos_base = 0.0 if reset else reached
        self._pos_time = GLib.get_monotonic_time() / 1e6
        if player is None:
            return
        key = self._track_key

        def done(position: int):
            if key == self._track_key:
                self._pos_base = float(position)
                self._pos_time = GLib.get_monotonic_time() / 1e6
                self.changed()

        player.fetch_position(done)

    @property
    def position(self) -> float:
        """Estimated position in microseconds."""
        player = self.current_player()
        length = (player.length or 0) if player else 0
        if self._status != "Playing":
            return self._pos_base
        elapsed = GLib.get_monotonic_time() / 1e6 - self._pos_time
        position = self._pos_base + elapsed * 1_000_000
        return min(position, length) if length else position

    # Lyrics

    def lyric_index(self) -> int:
        """Index of the line being sung (-1 before the first), or -1 if none."""
        seconds = self.position / 1_000_000
        index = -1
        for i, (start, _line) in enumerate(self.lyrics):
            if start <= seconds:
                index = i
            else:
                break
        return index

    def lyric_at(self, index: int) -> str:
        return self.lyrics[index][1] if 0 <= index < len(self.lyrics) else ""

    def lyric_lines(self) -> tuple[str, str] | None:
        """(current line, next line) at the current position, if synced."""
        if not self.lyrics:
            return None
        seconds = self.position / 1_000_000
        index = -1
        for i, (start, _line) in enumerate(self.lyrics):
            if start <= seconds:
                index = i
            else:
                break
        current = self.lyrics[index][1] if index >= 0 else ""
        upcoming = self.lyrics[index + 1][1] if index + 1 < len(self.lyrics) else ""
        return current, upcoming

    def _load_lyrics(self, player):
        self.lyrics = []
        self.lyrics_changed()
        if player is None or not player.title:
            self._lyrics_key = None
            return
        artist = ", ".join(a for a in (player.artist or []) if a)
        key = (
            player.title,
            artist,
            player.album or "",
            round((player.length or 0) / 1e6),
        )
        self._lyrics_key = key

        def work():
            return self._fetch_lyrics(*key)

        def done(lyrics):
            if key == self._lyrics_key:
                self.lyrics = lyrics or []
                self.lyrics_changed()
            return False

        def run():
            try:
                result = work()
            except Exception as e:
                logger.debug(f"[Lyrics] {e}")
                result = []
            GLib.idle_add(done, result)

        threading.Thread(target=run, daemon=True).start()

    @staticmethod
    def _fetch_lyrics(
        title: str, artist: str, album: str, duration: int
    ) -> list[tuple[float, str]]:
        os.makedirs(LYRICS_CACHE, exist_ok=True)
        digest = hashlib.sha1(f"{title}\n{artist}\n{duration}".encode()).hexdigest()
        path = os.path.join(LYRICS_CACHE, digest + ".json")
        try:
            with open(path) as f:
                return parse_lrc(json.load(f).get("synced") or "")
        except (OSError, ValueError):
            pass

        import requests

        headers = {"User-Agent": USER_AGENT}
        synced = ""
        params = {"track_name": title, "artist_name": artist}
        if album:
            params["album_name"] = album
        if duration:
            params["duration"] = str(duration)
        response = requests.get(
            f"{LRCLIB}/get", params=params, headers=headers, timeout=10
        )
        if response.ok:
            synced = response.json().get("syncedLyrics") or ""
        if not synced:
            # the exact match is strict about album and duration; search instead
            response = requests.get(
                f"{LRCLIB}/search",
                params={"track_name": title, "artist_name": artist},
                headers=headers,
                timeout=10,
            )
            if response.ok:
                for result in response.json():
                    if result.get("syncedLyrics"):
                        synced = result["syncedLyrics"]
                        break
        # remember misses too, so a song without lyrics isn't looked up again
        with open(path, "w") as f:
            json.dump({"synced": synced}, f)
        return parse_lrc(synced)
