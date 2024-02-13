import gi
import asyncio
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

class MprisPlayerManager(Service):
    __gsignals__ = SignalContainer(
        Signal("name-appeared", "run-last", None, ()),
        Signal("name-vanished", "run-last", None, ()),
        Signal("player-appeared", "run-last", None, ()),
        Signal("player-vanished", "run-last", None, ()),
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

    def on_name_appeard(self, player_manager, name):
        logger.info(f"[MprisPlayer] {name.name} appeared")
        self._manager.manage_player(Playerctl.Player.new_from_name(name))

    def on_name_vanished(self, player_manager, name):
        logger.info(f"[MprisPlayer] {name.name} vanished")

    def add_players(self):
        for player in self._manager.get_property("player-names"):
            self._manager.manage_player(Playerctl.Player.new_from_name(player))
        logger.info(f"[MprisPlayer] starting manager: {self._manager}")

    def get_players(self):
        return self._manager.get_property("players")
        

def on_metadata(player, metadata):
    if 'xesam:artist' in metadata.keys() and 'xesam:title' in metadata.keys():
        print('Now playing:')
        print('{artist} - {title}'.format(
            artist=metadata['xesam:artist'][0], title=metadata['xesam:title']))


def on_play(player, status):
    print('Playing at volume {}'.format(player.props.volume))


def on_pause(player, status):
    print('Paused the song: {}'.format(player.get_title()))

def playback_tim(player, status):
    print('current status {}'.format(player.get_position()))

# player.connect('playback-status::playing', on_play)
# player.connect('playback-status::paused', on_pause)
# player.connect('metadata', on_metadata)
# player.connect('seeked', playback_tim)

# mpris = MprisPlayerManager()
# for player in mpris.get_players():
#     player.connect('metadata', on_metadata)
#     player.connect('playback-status', on_play)

# main = GLib.MainLoop()
# main.run()