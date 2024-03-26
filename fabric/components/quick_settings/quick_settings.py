from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.scale import Scale
from fabric.widgets.image import Image
from services.mpris import MprisPlayerManager

from widgets.popup_window import PopupWindow
from widgets.player import PlayerBoxHandler
from widgets.bluetooth_box import BluetoothToggle

from fabric.widgets.wayland import Window

from fabric.bluetooth.service import BluetoothClient
from fabric.audio.service import Audio

bluetooth_icons = {
    "bluetooth": "󰂯",
    "bluetooth-off": "󰂲",
}

audio_icons = {"mute": "󰝟", "off": "󰖁", "high": "󰕾", "low": "󰕿", "medium": "󰖀"}

inhibit_overlay = False


class QuickSettings(Box):
    def __init__(self, **kwargs):
        super().__init__(orientation="v", name="quicksettings", **kwargs)
        self.mprisBox = PlayerBoxHandler(mprisplayer)
        self.bluetooth_toggle = BluetoothToggle(bluetooth_client)

        self.audio_slider = Scale(
            min_value=0, max_value=100, name="quicksettings-slider"
        )
        self.audio_slider.connect("change-value", self.on_scale_move)
        self.audio_slider.connect("button-release-event", self.unlock_overlay)
        audio.connect("speaker-changed", self.update_audio)

        self.add(
            Box(
                spacing=5,
                children=[Label(name="panel-text", label="󰓃"), self.audio_slider],
            )
        )
        self.add(self.bluetooth_toggle)
        self.add(self.mprisBox)

    def update_audio(self, *args):
        self.audio_slider.set_value(audio.speaker.volume)

    def unlock_overlay(self, *args):
        global inhibit_overlay
        inhibit_overlay = False

    def on_scale_move(self, scale, event, moved_pos):
        global inhibit_overlay
        inhibit_overlay = True
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


class AudioOverlay(PopupWindow):
    def __init__(self, **kwargs):
        self.audi_ind_box = Box()
        self.vol = 0
        audio.connect("speaker-changed", self.update_lable)
        self.icon = Image()

        super().__init__(
            transition_duration=100,
            anchor="right",
            transition_type="slide-left",
            child=Box(name="quicksettings", orientation="v", children=[self.audi_ind_box, self.icon], style="margin-right: 10px;"),
            **kwargs,
        )

    def update_lable(self, _):
        icon_name = "-".join(str(audio.speaker.icon).split("-")[0:2])
        self.icon.set_from_icon_name(icon_name + "-symbolic", 6)
        global inhibit_overlay
        if self.vol == audio.speaker.volume or inhibit_overlay:
            return
        self.vol = audio.speaker.volume
        self.audi_ind_box.set_style(
            "min-width: 25px; min-height: 200px;"
            + f"background-image: linear-gradient(to top, #64D9FF {round(self.vol)}%, #303030 {round(self.vol)}%);"
            + "border-radius: 200px; padding-right: 15px; margin-bottom:5px;"
        )
        self.popup_timeout()


QuickSettingsPopup = PopupWindow(
    transition_duration=100,
    anchor="top right",
    transition_type="slide-down",
    child=QuickSettings(),
)
