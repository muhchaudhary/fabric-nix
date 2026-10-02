from fabric.audio import Audio
from fabric.bluetooth import BluetoothClient
import gi

from fabric_config.services.brightness import Brightness
from fabric_config.services.clipboard_history import ClipboardHistory
from fabric_config.services.mpris_v2 import MprisPlayerManager
from fabric_config.services.screen_record import ScreenRecorder
from fabric_config.services.theme import ThemeService

gi.require_version("AstalNetwork", "0.1")
from gi.repository import AstalNetwork as Network  # noqa: E402

# Services
clipboard_history = ClipboardHistory()
mprisplayer = MprisPlayerManager()
bluetooth_client = BluetoothClient()
audio = Audio()
sc = ScreenRecorder()
brightness = Brightness()
network = Network.get_default()
theme = ThemeService()

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


def audio_icon_name(speaker) -> str:
    """Volume icon for a fabric audio stream (e.g. `audio.speaker`)."""
    if speaker is None:
        return audio_icons_names["off"]
    volume = round(speaker.volume)
    if speaker.muted or volume <= 0:
        return audio_icons_names["mute"]
    if volume >= 66:
        return audio_icons_names["high"]
    if volume >= 33:
        return audio_icons_names["medium"]
    return audio_icons_names["low"]
