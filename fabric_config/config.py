from fabric.audio.service import Audio
from fabric.bluetooth.service import BluetoothClient
import gi

from fabric_config.services.brightness import Brightness
from fabric_config.services.cava import Cava
from fabric_config.services.clipboard_history import ClipboardHistory
from fabric_config.services.mpris_v2 import MprisPlayerManager
from fabric_config.services.screen_record import ScreenRecorder
from fabric_config.services.theme import ThemeService
from fabric_config.services.wallpaper_accent import WallpaperAccent
from fabric_config.utils.process import run_command_async

gi.require_version("AstalNetwork", "0.1")
from gi.repository import AstalNetwork as Network  # noqa: E402
from gi.repository import GLib  # noqa: E402

# Services
clipboard_history = ClipboardHistory()
mprisplayer = MprisPlayerManager()
bluetooth_client = BluetoothClient()
audio = Audio()
sc = ScreenRecorder()
brightness = Brightness()
network = Network.get_default()
theme = ThemeService()
cava = Cava()  # audio levels, shared by whoever draws them
wallpaper_accent = WallpaperAccent()


# the whole theme's accent follows the wallpaper, tuned for light or dark
def _apply_theme_accent(*_):
    wallpaper_accent.apply_to_theme(theme.is_light)


wallpaper_accent.connect("changed", _apply_theme_accent)
theme.connect("notify::is-light", _apply_theme_accent)


# Cvc misses a default-device change that arrives before the device itself
# (typical when Bluetooth headphones connect): it can't resolve the name yet,
# records it as handled anyway and never retries, leaving `audio.speaker` on
# the old sink. Whenever devices come or go, ask the server and catch up.
_default_sync_source: int | None = None


def _sync_default_audio_streams():
    global _default_sync_source
    _default_sync_source = None
    for kind, cmd, streams in (
        ("speaker", "get-default-sink", lambda: audio.speakers),
        ("microphone", "get-default-source", lambda: audio.microphones),
    ):

        def on_done(ok: bool, stdout: str, _err: str, kind=kind, streams=streams):
            current = getattr(audio, kind)
            name = stdout.strip()
            if not ok or not name or (current and current.name == name):
                return
            for stream in streams():
                if stream.name == name:
                    audio.on_default_stream_changed(stream.id, kind)
                    return

        run_command_async(["pactl", cmd], on_done)
    return False


def _queue_default_audio_sync(*_):
    global _default_sync_source
    if _default_sync_source is None:
        _default_sync_source = GLib.timeout_add(300, _sync_default_audio_streams)


audio.connect("notify::speakers", _queue_default_audio_sync)
audio.connect("notify::microphones", _queue_default_audio_sync)

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
