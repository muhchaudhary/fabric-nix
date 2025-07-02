from fabric.audio import Audio
from fabric.bluetooth import BluetoothClient

from fabric_config.services.brightness import Brightness
from fabric_config.services.mpris_v2 import MprisPlayerManager
from fabric_config.services.screen_record import ScreenRecorder
from fabric_config.services.wifi import NetworkClient

# Services
mprisplayer = MprisPlayerManager()
bluetooth_client = BluetoothClient()
audio = Audio()
sc = ScreenRecorder()
brightness = Brightness()
network = NetworkClient()

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