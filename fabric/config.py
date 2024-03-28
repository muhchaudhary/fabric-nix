from services.mpris import MprisPlayerManager
from services.screen_record import ScreenRecorder
from fabric.audio.service import Audio
from fabric.bluetooth.service import BluetoothClient


# Services
mprisplayer = MprisPlayerManager()
bluetooth_client = BluetoothClient()
audio = Audio()
sc = ScreenRecorder()

# Icons
bluetooth_icons = {
    "bluetooth": "󰂯",
    "bluetooth-off": "󰂲",
}

audio_icons = {"mute": "󰝟", "off": "󰖁", "high": "󰕾", "low": "󰕿", "medium": "󰖀"}

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
