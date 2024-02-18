import gi
from loguru import logger
from dataclasses import dataclass
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
       Signal("track-artist", "run-first", None, (GLib.Array,)),
       Signal("player-abilities", "run-first", None, (GLib.Array,)),
       Signal("playback-status", "run-first",None, (Playerctl.PlaybackStatus,)),
       Signal("seeked", "run-first",None, (int,)),
       Signal("shuffle", "run-first",None, (bool,)),
    )

class MprisPlayerManager(Service):
    __gsignals__ = SignalContainer(
        Signal("player-appeared", "run-first", None, (Playerctl.PlayerManager,Playerctl.Player,)),
        Signal("player-vanished", "run-first", None, (Playerctl.PlayerManager,Playerctl.Player,)),
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

    def on_name_appeard(self, player_manager: Playerctl.PlayerManager, player: Playerctl.Player):
        logger.info(f"[MprisPlayer] {player.name} appeared")
        # This might cause memory leak (haven't checked)
        new_player = Playerctl.Player.new_from_name(player)
        self._manager.manage_player(new_player)
        self.emit("player-appeared",player_manager, new_player)

    def on_name_vanished(self, player_manager, player):
        logger.info(f"[MprisPlayer] {player.name} vanished")
        self.emit("player-vanished",player_manager, player)

    def add_players(self):
        for player in self._manager.get_property("player-names"):
            self._manager.manage_player(Playerctl.Player.new_from_name(player))
        logger.info(f"[MprisPlayer] starting manager: {self._manager}")

    def get_players(self):
        return self._manager.get_property("players")