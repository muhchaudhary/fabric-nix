from typing import Any
import gi
from loguru import logger
from fabric.service import Service, Signal, SignalContainer, Property
from fabric.utils import bulk_connect


class PlayerctlImportError(ImportError):
    def __init__(self, *args):
        super().__init__(
            "Playerctl is not installed, please install it first",
            *args,
        )


try:
    gi.require_version("Playerctl", "2.0")
    from gi.repository import Playerctl  # type: ignore
except ValueError:
    raise PlayerctlImportError()

# TODO: consider building my own mpris service using dbus rather than playerctl


class MprisPlayer(Service):
    __gsignals__ = SignalContainer(
        Signal("position", "run-first", None, (int,)),
        Signal("exit", "run-first", None, (bool,)),
        Signal("changed", "run-first", None, ()),  # type: ignore
    )

    def __init__(
        self,
        player: Playerctl.Player,
        **kwargs,
    ):
        self._player: Playerctl.Player = player
        super().__init__(**kwargs)

        bulk_connect(
            self._player,
            {
                "exit": self.on_player_exit,
                "metadata": lambda *args: self.update_status(),
                "playback-status": lambda *args: self.notifier("playback-status"),
                "shuffle": lambda *args: self.notifier("shuffle"),
                "loop-status": lambda *args: self.notifier("loop-status"),
            },
        )

    def update_status(self):
        for prop in self.list_properties():
            self.notifier(prop.name)

    def notifier(self, name: str, args=None):
        self.notify(name)
        self.emit("changed")
        return

    def on_player_exit(self, player):
        self.emit("exit", True)
        del self._player
        # TODO check if this is needed
        del self

    # Player Functions
    def toggle_shuffle(self):
        self._player.set_shuffle(
            not self._player.props.shuffle
        ) if self.can_shuffle else None

    def play_pause(self):
        self._player.play_pause() if self.can_pause else None

    def next(self):
        self._player.next() if self.can_go_next else None

    def previous(self):
        self._player.previous() if self.can_go_previous else None

    def set_position(self, pos: int):
        self._player.set_position(pos) if self.can_seek else None

    def get_position(self) -> int:
        return self._player.get_position() if self.can_seek else None  # type: ignore

    # Because of type error issues (do test)
    def _get_metadata(self) -> dict:
        return self._player.get_property("metadata")

    # Properties
    # TODO DICT NOT SUPPORTED?

    @Property(value_type=int, flags="readable")
    def position(self) -> int:
        return self._player.get_property("position")

    @Property(value_type=str, flags="readable")
    def metadata(self) -> dict:
        return self._get_metadata()

    @Property(value_type=str or None, flags="readable")
    def arturl(self) -> str | None:
        if "mpris:artUrl" in self._get_metadata().keys():
            return self._get_metadata()["mpris:artUrl"]
        return None

    @Property(value_type=str or None, flags="readable")
    def length(self) -> str | None:
        if "mpris:length" in self._get_metadata().keys():
            return self._get_metadata()["mpris:length"]
        return None

    @Property(value_type=str, flags="readable")
    def artist(self) -> str:
        return self._player.get_artist()

    @Property(value_type=str, flags="readable")
    def album(self) -> str:
        return self._player.get_album()

    @Property(value_type=str, flags="readable")
    def title(self):
        return self._player.get_title()

    @Property(value_type=bool, default_value=False, flags="readable")
    def shuffle(self) -> bool:
        return self._player.get_property("shuffle")

    @Property(value_type=str, flags="readable")
    def playback_status(self) -> str:
        return {
            Playerctl.PlaybackStatus.PAUSED: "paused",
            Playerctl.PlaybackStatus.PLAYING: "playing",
            Playerctl.PlaybackStatus.STOPPED: "stopped",
        }.get(self._player.get_property("playback_status"), "unknown")

    @Property(value_type=str, flags="readable")
    def loop_status(self) -> str:
        return {
            Playerctl.LoopStatus.NONE: "none",
            Playerctl.LoopStatus.TRACK: "track",
            Playerctl.LoopStatus.PLAYLIST: "playlist",
        }.get(self._player.get_property("loop_status"), "unknown")

    @Property(value_type=bool, default_value=False, flags="readable")
    def can_go_next(self) -> bool:
        return self._player.get_property("can_go_next")

    @Property(value_type=bool, default_value=False, flags="readable")
    def can_go_previous(self) -> bool:
        return self._player.get_property("can_go_previous")

    @Property(value_type=bool, default_value=False, flags="readable")
    def can_seek(self) -> bool:
        return self._player.get_property("can_seek")

    @Property(value_type=bool, default_value=False, flags="readable")
    def can_pause(self) -> bool:
        return self._player.get_property("can_pause")

    @Property(value_type=bool, default_value=False, flags="readable")
    def can_shuffle(self) -> bool:
        try:
            self._player.set_shuffle(self._player.get_property("shuffle"))
            return True
        except:
            return False


class MprisPlayerManager(Service):
    __gsignals__ = SignalContainer(
        Signal("player-appeared", "run-first", None, (Playerctl.Player,)),
        Signal("player-vanished", "run-first", None, (str,)),
    )

    def __init__(
        self,
        **kwargs,
    ):
        self._manager = Playerctl.PlayerManager.new()
        bulk_connect(
            self._manager,
            {
                "name-appeared": self.on_name_appeard,
                "name-vanished": self.on_name_vanished,
            },
        )
        self.add_players()
        super().__init__(**kwargs)

    def on_name_appeard(self, manager, player_name: Playerctl.PlayerName):
        logger.info(f"[MprisPlayer] {player_name.name} appeared")
        new_player = Playerctl.Player.new_from_name(player_name)
        manager.manage_player(new_player)
        self.emit("player-appeared", new_player)

    def on_name_vanished(self, manager, player_name: Playerctl.PlayerName):
        logger.info(f"[MprisPlayer] {player_name.name} vanished")
        self.emit("player-vanished", player_name.name)

    def add_players(self):
        for player in self._manager.get_property("player-names"):
            self._manager.manage_player(Playerctl.Player.new_from_name(player))
        logger.info(f"[MprisPlayer] starting manager: {self._manager}")

    def get_players(self):
        return self._manager.get_property("players")
