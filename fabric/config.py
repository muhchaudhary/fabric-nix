from services.brightness import Brightness
from services.mpris import MprisPlayerManager
from services.screen_record import ScreenRecorder

from fabric.audio.service import Audio
from fabric.bluetooth.service import BluetoothClient

# Services
mprisplayer = MprisPlayerManager()
bluetooth_client = BluetoothClient()
audio = Audio()
sc = ScreenRecorder()
brightness = Brightness()

# Icons
bluetooth_icons = {
    "bluetooth": "󰂯",
    "bluetooth-off": "󰂲",
}
bluetooth_icons_names = {
    "bluetooth": "bluetooth-active-symbolic",
    "bluetooth-off": "bluetooth-disabled-symbolic",
}


audio_icons = {"mute": "󰝟", "off": "󰖁", "high": "󰕾", "low": "󰕿", "medium": "󰖀"}
audio_icons_names = {
    "mute": "audio-volume-muted",
    "off": "audio-volume-muted",
    "low": "audio-volume-low",
    "medium": "audio-volume-medium",
    "high": "audio-volume-high",
}

battery_icons = {
    0: "󱃍",
    10: "󰁺",
    20: "󰁻",
    30: "󰁼",
    40: "󰁽",
    50: "󰁾",
    60: "󰁿",
    70: "󰂀",
    80: "󰂁",
    90: "󰂂",
    100: "󰁹",
}

battery_charging_icons = {
    0: "󰢟",
    10: "󰢜",
    20: "󰂆",
    30: "󰂇",
    40: "󰂈",
    50: "󰢝",
    60: "󰂉",
    70: "󰢞",
    80: "󰂊",
    90: "󰂋",
    100: "󰂅",
}
