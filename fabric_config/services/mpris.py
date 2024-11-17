import gi
from fabric.core.service import Service, Signal, Property
from fabric.utils import bulk_connect
from gi.repository import GLib  # type: ignore
from loguru import logger


class PlayerctlImportError(ImportError):
    def __init__(self, *args):
        super().__init__(
            "Playerctl is not installed, please install it first",
            *args,
        )


try:
    gi.require_version("Playerctl", "2.0")
    from gi.repository import Playerctl
    # from gi.repository import Playerctl  # type: ignore
except ValueError:
    raise PlayerctlImportError

# TODO: (not needed) consider building my own mpris service using dbus rather than playerctl


class MprisPlayer(Service):
    @Signal
    def exit(self, value: bool) -> bool: ...

    @Signal
    def changed(self) -> None: ...

    def __init__(
        self,
        player: Playerctl.Player,
        **kwargs,
    ):
        self._signal_connectors: dict = {}
        self._player: Playerctl.Player = player
        super().__init__(**kwargs)
        for sn in ["playback-status", "loop-status", "shuffle", "volume", "seeked"]:
            self._signal_connectors[sn] = self._player.connect(
                sn,
                lambda *args, sn=sn: self.notifier(sn, args),
            )

        self._signal_connectors["exit"] = self._player.connect(
            "exit",
            self.on_player_exit,
        )
        self._signal_connectors["metadata"] = self._player.connect(
            "metadata",
            lambda *args: self.update_status(),
        )
        GLib.idle_add(lambda *args: self.update_status_once())

    def update_status(self):
        for prop in [
            "metadata",
            "title",
            "artist",
            "arturl",
            "length",
        ]:
            self.notifier(prop) if self.get_property(prop) is not None else None
        for prop in [
            "can-seek",
            "can-pause",
            "can-shuffle",
            "can-go-next",
            "can-go-previous",
        ]:
            self.notifier(prop)

    def update_status_once(self):
        for prop in self.list_properties():  # type: ignore
            self.notifier(prop.name)

    def notifier(self, name: str, args=None):
        self.notify(name)
        self.emit("changed")  # type: ignore

    def on_player_exit(self, player):
        for id in self._signal_connectors.values():
            try:
                self._player.disconnect(id)
            except Exception:
                pass
        del self._player
        self.emit("exit", True)  # type: ignore
        # TODO check if this is needed
        del self

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle if self.can_shuffle else self.shuffle

    def play_pause(self):
        self._player.play_pause() if self.can_pause else None

    def next(self):
        self._player.next() if self.can_go_next else None

    def previous(self):
        self._player.previous() if self.can_go_previous else None

    # Properties
    @Property(str, "readable")
    def player_name(self) -> int:
        return self._player.get_property("player-name")  # type: ignore

    @Property(int, "read-write", default_value=0)
    def position(self) -> int:
        return self._player.get_property("position")  # type: ignore

    @position.setter
    def position(self, new_pos: int):
        self._player.set_position(new_pos)

    @Property(object, "readable")
    def metadata(self) -> dict:
        return self._player.get_property("metadata")  # type: ignore

    @Property(str or None, "readable")
    def arturl(self) -> str | None:
        if "mpris:artUrl" in self.metadata.keys():  # type: ignore
            return self.metadata["mpris:artUrl"]  # type: ignore
        return None

    @Property(str or None, "readable")
    def length(self) -> str | None:
        if "mpris:length" in self.metadata.keys():  # type: ignore
            return self.metadata["mpris:length"]  # type: ignore
        return None

    @Property(str, "readable")
    def artist(self) -> str:
        return self._player.get_artist()  # type: ignore

    @Property(str, "readable")
    def album(self) -> str:
        return self._player.get_album()  # type: ignore

    @Property(str, "readable")
    def title(self):
        return self._player.get_title()

    @Property(bool, "read-write", default_value=False)
    def shuffle(self) -> bool:
        return self._player.get_property("shuffle")  # type: ignore

    @shuffle.setter
    def shuffle(self, do_shuffle: bool):
        self.notifier("shuffle")
        return self._player.set_shuffle(do_shuffle)

    @Property(str, "readable")
    def playback_status(self) -> str:
        return {
            Playerctl.PlaybackStatus.PAUSED: "paused",
            Playerctl.PlaybackStatus.PLAYING: "playing",
            Playerctl.PlaybackStatus.STOPPED: "stopped",
        }.get(self._player.get_property("playback_status"), "unknown")  # type: ignore

    @Property(str, "read-write")
    def loop_status(self) -> str:
        return {
            Playerctl.LoopStatus.NONE: "none",
            Playerctl.LoopStatus.TRACK: "track",
            Playerctl.LoopStatus.PLAYLIST: "playlist",
        }.get(self._player.get_property("loop_status"), "unknown")  # type: ignore

    @loop_status.setter
    def loop_status(self, status: str):
        loop_status = {
            "none": Playerctl.LoopStatus.NONE,
            "track": Playerctl.LoopStatus.TRACK,
            "playlist": Playerctl.LoopStatus.PLAYLIST,
        }.get(status)
        self._player.set_loop_status(loop_status) if loop_status else None

    @Property(bool, "readable", default_value=False)
    def can_go_next(self) -> bool:
        return self._player.get_property("can_go_next")  # type: ignore

    @Property(bool, "readable", default_value=False)
    def can_go_previous(self) -> bool:
        return self._player.get_property("can_go_previous")  # type: ignore

    @Property(bool, "readable", default_value=False)
    def can_seek(self) -> bool:
        return self._player.get_property("can_seek")  # type: ignore

    @Property(bool, "readable", default_value=False)
    def can_pause(self) -> bool:
        return self._player.get_property("can_pause")  # type: ignore

    @Property(bool, "readable", default_value=False)
    def can_shuffle(self) -> bool:
        try:
            self._player.set_shuffle(self._player.get_property("shuffle"))
            return True
        except Exception:
            return False

    @Property(bool, "readable", default_value=False)
    def can_loop(self) -> bool:
        try:
            self._player.set_shuffle(self._player.get_property("shuffle"))
            return True
        except Exception:
            return False


class MprisPlayerManager(Service):
    @Signal
    def player_appeared(self, player: Playerctl.Player) -> Playerctl.Player: ...

    @Signal
    def player_vanished(self, player_name: str) -> str: ...

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
        self.emit("player-appeared", new_player)  # type: ignore

    def on_name_vanished(self, manager, player_name: Playerctl.PlayerName):
        logger.info(f"[MprisPlayer] {player_name.name} vanished")
        self.emit("player-vanished", player_name.name)  # type: ignore

    def add_players(self):
        for player in self._manager.get_property("player-names"):  # type: ignore
            self._manager.manage_player(Playerctl.Player.new_from_name(player))  # type: ignore

    @Property(object, "readable")
    def players(self):
        return self._manager.get_property("players")  # type: ignore
