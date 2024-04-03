import config
from widgets.bluetooth_box import BluetoothToggle
from widgets.player import PlayerBoxHandler
from widgets.popup_window import PopupWindow

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.scale import Scale


class QuickSettingsAudioScale(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="quicksettings-box",
            orientation="v",
            h_expand=True,
            **kwargs,
        )
        # self.label = Label("Sound", h_align="start")
        self.icon_name = ""
        self.audio_slider = Scale(
            min_value=0, max_value=100, name="quicksettings-slider", h_expand=True
        )
        self.audio_slider.connect("change-value", self.on_scale_move)
        config.audio.connect("speaker-changed", self.update_audio)

        self.icon = Image()
        self.mute_button = Button(icon_image=self.icon, name="panel-button")
        self.mute_button.connect("clicked", self.mute_audio)

        # self.add(self.label)
        self.add(Box(spacing=5, children=[self.mute_button, self.audio_slider]))

    def update_audio(self, *args):
        self.audio_slider.set_sensitive(not config.audio.speaker.is_muted)
        self.audio_slider.set_value(config.audio.speaker.volume)
        self.mute_button.set_name(
            "panel-button-active"
        ) if config.audio.speaker.is_muted else self.mute_button.set_name(
            "panel-button"
        )
        icon_name = "-".join(str(config.audio.speaker.icon).split("-")[0:2])
        if icon_name != self.icon_name:
            self.icon_name = icon_name
            self.icon.set_from_icon_name(icon_name + "-symbolic", 1)
            self.icon.set_pixel_size(28)

    def mute_audio(self, *args):
        config.audio.speaker.is_muted = not config.audio.speaker.is_muted

    def on_scale_move(self, scale, event, moved_pos):
        config.audio.speaker.volume = moved_pos


class QuickSettingsBrightnessScale(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="quicksettings-box",
            orientation="v",
            h_expand=True,
            **kwargs,
        )
        # self.label = Label("Display", h_align="start")
        if config.brightness.max_screen == -1:
            self.set_name("disabled")
            self.set_visible(False)
            return
        self.brightness_slider = Scale(
            min_value=0,
            max_value=config.brightness.max_screen,
            name="quicksettings-slider",
            value=config.brightness.screen_brightness,
            h_expand=True,
        )

        self.brightness_slider.connect("change-value", self.on_brightness_scale_move)
        config.brightness.connect("screen", self.on_brightness_changed)

        self.icon = Image(icon_name="display-brightness-symbolic", pixel_size=28)
        self.icon_button = Button(icon_image=self.icon, name="panel-button")

        self.add(Box(spacing=5, children=[self.icon_button, self.brightness_slider]))

    def on_brightness_scale_move(self, scale, event, moved_pos):
        config.brightness.screen_brightness = moved_pos

    def on_brightness_changed(self, *args):
        self.brightness_slider.set_value(config.brightness.screen_brightness)  # type: ignore


class QuickSettingsButtonBox(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="v",
            h_align="start",
            v_align="start",
            # h_expand=True,
            **kwargs,
        )
        self.bluetooth_toggle = BluetoothToggle(config.bluetooth_client)
        self.add(self.bluetooth_toggle)


class QuickSettings(Box):
    def __init__(self, **kwargs):
        super().__init__(orientation="v", spacing=10, name="quicksettings", **kwargs)
        self.mprisBox = PlayerBoxHandler(config.mprisplayer)
        self.audio_slider_box = QuickSettingsAudioScale()
        self.screen_slider_box = QuickSettingsBrightnessScale()
        self.buttons_box = QuickSettingsButtonBox()
        self.add(self.buttons_box)
        self.add(self.audio_slider_box)
        self.add(self.screen_slider_box)
        self.add(self.mprisBox)


class QuickSettingsButton(Button):
    def __init__(self, **kwargs):
        super().__init__(name="panel-button", **kwargs)

        self.bluetooth_icon = Image(
            name="panel-icon",
            icon_name=config.bluetooth_icons_names["bluetooth"],
            pixel_size=20,
            style="color: #51A4E7;",
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
            self.audio_icon.set_from_icon_name(config.audio_icons_names["mute"], 1)
            return
        if 66 <= vol:
            self.audio_icon.set_from_icon_name(config.audio_icons_names["high"], 1)
        elif 33 <= vol < 66:
            self.audio_icon.set_from_icon_name(config.audio_icons_names["medium"], 1)
        elif 0 < vol < 33:
            self.audio_icon.set_from_icon_name(config.audio_icons_names["low"], 1)
        else:
            self.audio_icon.set_from_icon_name(config.audio_icons_names["off"], 1)

        self.audio_icon.set_pixel_size(20)

    def on_click(self, *args):
        QuickSettingsPopup.toggle_popup()


QuickSettingsPopup = PopupWindow(
    transition_duration=200,
    anchor="top right",
    transition_type="slide-down",
    child=QuickSettings(),
    enable_inhibitor=True,
)
