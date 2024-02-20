import gi
from loguru import logger
from fabric.service import *
from fabric.utils import (
    bulk_connect
)
from gi.repository import GLib

class PlayerctlImportError(ImportError):
    def __init__(self, *args):
        super().__init__(
            "playerctl is not installed, please install it first",
            *args,
        )

try:
    gi.require_version('Playerctl', '2.0')
    from gi.repository import Playerctl
except:
    raise PlayerctlImportError()

# TODO: Build Out MprisPlayer Service

class MprisPlayer(Service):
    __gsignals__ = SignalContainer(
       Signal("track-title", "run-first", None, (str,)),
       Signal("track-artist", "run-first", None, (str,)),
       Signal("track-length", "run-first", None, (int,)),
       Signal("track-arturl", "run-first", None, (str,)),
       Signal("playback-status", "run-first",None, (str,)),
       Signal("seeked", "run-first",None, (int,)),
       Signal("shuffle", "run-first",None, (bool,)),
       Signal("exit", "run-first", None, (bool,)),
    )
    def __init__(
        self,
        player: Playerctl.Player,
        **kwargs,
    ):
        self._player = player
        # missing can_play (has side effect)
        self.can_go_next = self._player.get_property("can-go-next")
        self._can_go_next = self._player.get_property("can-go-next")
        self.can_go_previous = self._player.get_property("can_go_previous")
        self.can_pause = self._player.get_property("can_pause")
        self.can_seek = self._player.get_property("can_seek")
        bulk_connect(
            self._player,
            {
                "exit": self.on_player_exit,
                "playback-status": self.on_playback_update,
                "shuffle": self.on_shuffle,
                "metadata": self.on_metadata_update,
            }
        )
        super().__init__(**kwargs)
        self.on_metadata_update(self._player,self._player.get_property("metadata"))
        self._player.connect("notify::can-go-next", lambda x,y: logger.error(f"AHHHADAFDSFDSFSFSFFDSF EUFH {x} {y}"))

        self._player.bind_property(
            "can-go-next",
            self,
            "can-skip-n",
            GObject.BindingFlags.DEFAULT,
        )


    # callback function
    def update_abilities(self):
        logger.info(f"can go next? {self._player.get_property('can_go_next')}")
        self.notify("can-skip-n")
        self.can_go_next = self._player.get_property("can_go_next")
        self.can_go_previous = self._player.get_property("can_go_previous")
        self.can_pause = self._player.get_property("can_pause")
        self.can_seek = self._player.get_property("can_seek")

    def on_player_exit(self, player):
        self.emit("exit", True)
        del self._player
        # TODO check if this is needed
        del self
    
    def on_playback_update(self, player, status):
        _status = (
            {
                Playerctl.PlaybackStatus.PAUSED: "paused",
                Playerctl.PlaybackStatus.PLAYING: "playing",
                Playerctl.PlaybackStatus.STOPPED: "stopped",
            }.get(status)
        )
        logger.info(f"[PLAYER] status changed to {_status}")
        self.emit("playback-status", _status)

    def on_shuffle(self, player, status):
        logger.info(f"[Player] shuffle status changed to {status}")
        self.emit("shuffle", status)

    def on_metadata_update(self, player, metadata):
        self.update_abilities()
        keys = metadata.keys()
        # or we can do if self.can_seek
        if "mpris:length" in keys:
            self.emit("track-length", metadata["mpris:length"])
        if "mpris:artUrl" in keys:
            self.emit("track-arturl", metadata["mpris:artUrl"])
        if "xesam:title" in keys:
            self.emit("track-title", metadata["xesam:title"])
        if "xesam:artist" in keys:
            self.emit("track-artist", ', '.join(metadata["xesam:artist"]))

    def initilize(self):
        self.on_metadata_update(self.play_pause,
                                self._player.get_property("metadata"))
        self.on_playback_update(self._player, self.get_playback_status())
        self.on_shuffle(self._player, self.get_shuffle())


    # player function
    def play_pause(self):
        self._player.play_pause() if self.can_pause else None

    def next(self):
        self._player.next() if self._player.get_property("can-go-next") else None

    def previous(self):
        self._player.previous() if self.can_go_previous else None

    def set_position(self, pos):
        self._player.set_position(pos) if self.can_seek else None

    def set_shuffle(self, shuffle):
        self._player.set_shuffle(shuffle)

    def get_shuffle(self):
        return self._player.get_property("shuffle")

    def get_position(self):
        return self._player.get_position() if self.can_seek else None

    def get_playback_status(self):
        self.on_playback_update(
            self._player,
            self._player.get_property("playback-status")
        )
    # Setters
    @Property(value_type=bool,default_value=True,flags="read-write")
    def can_skip_n(self):
        return self.can_go_next

    @can_skip_n.setter
    def can_skip_n(self, value: bool):
        self._can_go_next = value


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
            }
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