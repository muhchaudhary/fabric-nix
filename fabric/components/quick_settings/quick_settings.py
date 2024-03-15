from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.scale import Scale

from services.mpris import MprisPlayerManager

from widgets.popup_window import PopupWindow
from widgets.player import PlayerBoxHandler
from widgets.bluetooth_box import BluetoothToggle

from fabric.bluetooth.service import BluetoothClient
from fabric.audio.service import Audio

bluetooth_icons = {
    "bluetooth": "󰂯",
    "bluetooth-off": "󰂲",
}

audio_icons = {"mute": "󰝟", "off": "󰖁", "high": "󰕾", "low": "󰕿", "medium": "󰖀"}


class QuickSettings(Box):
    def __init__(self, **kwargs):
        super().__init__(orientation="v", name="quicksettings", **kwargs)
        self.mprisBox = PlayerBoxHandler(mprisplayer)
        self.bluetooth_toggle = BluetoothToggle(bluetooth_client)

        self.audio_slider = Scale(min_value=0, max_value=100,name="quicksettings-slider")
        self.audio_slider.connect("change-value", self.on_scale_move)
        audio.connect("speaker-changed", self.update_audio)

        self.add(Box(spacing=5,children=[Label(name="panel-text", label="󰓃"),self.audio_slider]))
        self.add(self.bluetooth_toggle)
        self.add(self.mprisBox)

    def update_audio(self, *args):
        self.audio_slider.set_value(audio.speaker.volume)

    def on_scale_move(self, scale, event, moved_pos):
        audio.speaker.volume = moved_pos


class QuickSettingsButton(Button):
    def __init__(self, **kwargs):
        super().__init__(name="panel-button", **kwargs)

        self.bluetooth_icon = Label(name="panel-icon")
        bluetooth_client.connect("notify::enabled", self.bluetooth_set)

        self.audio_icon = Label(name="panel-icon")
        audio.connect("speaker-changed", self.update_audio)

        self.add(Box(children=[self.bluetooth_icon, self.audio_icon]))
        self.connect("clicked", self.on_click)

    def update_audio(self, *args):
        vol = audio.speaker.volume
        if audio.speaker.is_muted:
            self.audio_icon.set_label(audio_icons["mute"])
            return
        if 66 <= vol:
            self.audio_icon.set_label(audio_icons["high"])
        elif 33 <= vol < 66:
            self.audio_icon.set_label(audio_icons["medium"])
        elif 0 < vol < 33:
            self.audio_icon.set_label(audio_icons["low"])
        else:
            self.audio_icon.set_label(audio_icons["off"])

    def bluetooth_set(self, *args):
        status = bluetooth_client.get_property("enabled")
        self.bluetooth_icon.set_label(
            bluetooth_icons["bluetooth"]
        ) if status else self.bluetooth_icon.set_label("")

    def on_click(self, *args):
        QuickSettingsPopup.toggle_popup()


mprisplayer = MprisPlayerManager()
bluetooth_client = BluetoothClient()
audio = Audio()

QuickSettingsPopup = PopupWindow(
    transition_duration=100,
    anchor="top right",
    transition_type="slide-down",
    child=QuickSettings(),
)
