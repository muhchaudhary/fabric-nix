from fabric.audio import Audio
from fabric.bluetooth import BluetoothClient
import gi

from fabric_config.services.brightness import Brightness
from fabric_config.services.mpris_v2 import MprisPlayerManager
from fabric_config.services.screen_record import ScreenRecorder
gi.require_version("AstalNetwork", "0.1")
from gi.repository import AstalNetwork as Network

# Services
mprisplayer = MprisPlayerManager()
bluetooth_client = BluetoothClient()
audio = Audio()
sc = ScreenRecorder()
brightness = Brightness()
network = Network.get_default()

bluetooth_icons_names = {
    "bluetooth": "bluetooth-active-symbolic",
    "bluetooth-off": "bluetooth-disabled-symbolic",
}


audio_icons_names = {
    "mute": "audio-volume-muted-symbolic",
    "off": "audio-volume-muted-symbolic",
    "low": "audio-volume-low-symbolic",
    "medium": "audio-volume-medium-symbolic",
    "high": "audio-volume-high-symbolic",
}