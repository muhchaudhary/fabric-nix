from fabric.audio import Audio
from fabric.bluetooth import BluetoothClient

from services.brightness import Brightness
from services.mpris import MprisPlayerManager
from services.screen_record import ScreenRecorder
from services.wifi import NetworkClient
from services.notifications_astal_v2 import NotificationServer

# Services
mprisplayer = MprisPlayerManager()
bluetooth_client = BluetoothClient()
audio = Audio()
sc = ScreenRecorder()
brightness = Brightness()
network = NetworkClient()
notification_server = NotificationServer()

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
    "mute": "audio-volume-muted-symbolic",
    "off": "audio-volume-muted-symbolic",
    "low": "audio-volume-low-symbolic",
    "medium": "audio-volume-medium-symbolic",
    "high": "audio-volume-high-symbolic",
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

battery_gtk_icon = {
    0: "battery-empty",
    25: "battery-caution",
    50: "battery-low",
    75: "battery-good",
    100: "battery-full",
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
