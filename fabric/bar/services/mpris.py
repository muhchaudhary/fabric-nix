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
        self.player = player
        self.instance_name = self.player.get_property("player-name")
        # missing can_play (has side effect)
        self.can_go_next = self.player.get_property("can_go_next")
        self.can_go_previous = self.player.get_property("can_go_previous")
        self.can_pause = self.player.get_property("can_pause")
        self.can_seek = self.player.get_property("can_seek")
        bulk_connect(
            self.player,
            {
                "exit": self.on_player_exit,
                "playback-status": self.on_playback_update,
                "shuffle": self.on_shuffle,
                "metadata": self.on_metadata_update,
                # "seeked": self.on_test_for_seek,
            }
        )
        super().__init__(**kwargs)
        self.on_metadata_update(self.player,self.player.get_property("metadata"))


    # callback function
    def update_abilities(self):
        self.can_go_next = self.player.get_property("can_go_next")
        self.can_go_previous = self.player.get_property("can_go_previous")
        self.can_pause = self.player.get_property("can_pause")
        self.can_seek = self.player.get_property("can_seek")

    def on_player_exit(self, player):
        self.emit("exit", True)
        del self.player
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
        self.update_abilities()
        self.on_metadata_update(self.play_pause,
                                self.player.get_property("metadata"))
        self.on_playback_update(self.player, self.get_playback_status())
        self.on_shuffle(self.player, self.get_shuffle())


    # player function
    def play_pause(self):
        self.player.play_pause() if self.can_pause else None

    def next(self):
        self.player.next() if self.player.get_property("can_go_next") else None

    def previous(self):
        self.player.previous() if self.can_go_previous else None

    def set_position(self, pos):
        self.player.set_position(pos) if self.can_seek else None

    def set_shuffle(self, shuffle):
        self.player.set_shuffle(shuffle)

    def get_shuffle(self):
        return self.player.get_property("shuffle")

    def get_position(self):
        return self.player.get_position() if self.can_seek else None

    def get_playback_status(self):
        self.on_playback_update(
            self.player,
            self.player.get_property("playback-status")
        )

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