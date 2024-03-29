import config
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.scale import Scale
from fabric.widgets.button import Button
from fabric.widgets.image import Image

from widgets.popup_window import PopupWindow
from widgets.player import PlayerBoxHandler
from widgets.bluetooth_box import BluetoothToggle


class QuickSettings(Box):
    def __init__(self, **kwargs):
        super().__init__(orientation="v", name="quicksettings", **kwargs)
        self.mprisBox = PlayerBoxHandler(config.mprisplayer)
        self.bluetooth_toggle = BluetoothToggle(config.bluetooth_client)

        self.audio_slider = Scale(
            min_value=0, max_value=100, name="quicksettings-slider"
        )
        self.audio_slider.connect("change-value", self.on_scale_move)
        config.audio.connect("speaker-changed", self.update_audio)

        self.add(
            Box(
                spacing=5,
                children=[Label(name="panel-text", label="󰓃"), self.audio_slider],
            )
        )
        self.add(self.bluetooth_toggle)
        self.add(self.mprisBox)

    def update_audio(self, *args):
        self.audio_slider.set_value(config.audio.speaker.volume)

    def on_scale_move(self, scale, event, moved_pos):
        config.audio.speaker.volume = moved_pos


class QuickSettingsButton(Button):
    def __init__(self, **kwargs):
        super().__init__(name="panel-button", **kwargs)

        self.bluetooth_icon = Image(
            name="panel-icon",
            icon_name=config.bluetooth_icons_names["bluetooth"],
            pixel_size=20,
        )
        config.bluetooth_client.bind_property(
            "enabled",
            self.bluetooth_icon,
            "visible",
        )

        self.audio_icon = Image(name="panel-icon")
        config.audio.connect("speaker-changed", self.update_audio)

        self.add(Box(children=[self.bluetooth_icon, self.audio_icon]))
        self.connect("clicked", self.on_click)

    def update_audio(self, *args):
        vol = config.audio.speaker.volume
        if config.audio.speaker.is_muted:
            self.audio_icon.set_from_icon_name(config.audio_icons_names["mute"], -1)
            return
        if 66 <= vol:
            self.audio_icon.set_from_icon_name(config.audio_icons_names["high"], -1)
        elif 33 <= vol < 66:
            self.audio_icon.set_from_icon_name(config.audio_icons_names["medium"], -1)
        elif 0 < vol < 33:
            self.audio_icon.set_from_icon_name(config.audio_icons_names["low"], -1)
        else:
            self.audio_icon.set_from_icon_name(config.audio_icons_names["off"], -1)

        self.audio_icon.set_pixel_size(28)

    def on_click(self, *args):
        QuickSettingsPopup.toggle_popup()


QuickSettingsPopup = PopupWindow(
    transition_duration=100,
    anchor="top right",
    transition_type="slide-down",
    child=QuickSettings(),
)
