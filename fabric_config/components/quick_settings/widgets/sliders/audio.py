from fabric.audio.service import Audio
from fabric.widgets.button import Button
from fabric.widgets.image import Image

import fabric_config.config as config
from fabric_config.components.quick_settings.widgets.quick_settings_scale import (
    QuickSettingsScale,
)
from fabric_config.components.quick_settings.widgets.submenus.audio import (
    AudioSubMenu,
)


class AudioSlider(QuickSettingsScale):
    def __init__(self, client: Audio):
        self.client: Audio = client
        self.icon_name = ""
        super().__init__(min=0, max=100, pixel_size=28)
        self.scale.connect("change-value", self.on_scale_move)
        self.client.connect("speaker-changed", self.on_speaker_change)
        self.icon_button.connect("clicked", self.on_button_click)

        # the arrow opens the output/input picker (QuickSettings places it
        # below the slider and keeps one submenu open at a time)
        self.submenu = AudioSubMenu(config.audio_devices)
        self.reveal_button = Button(
            image=Image(icon_name="pan-end-symbolic", icon_size=16),
            tooltip_text="Choose output and input",
            style_classes=[
                "button-basic",
                "button-basic-props",
                "button-border",
                "quicksettings-reveal",
            ],
        )
        self.row.add(self.reveal_button)
        self.submenu.revealer.connect("notify::reveal-child", self.on_reveal)

    def on_scale_move(self, _, __, moved_pos):
        self.client.speaker.volume = moved_pos

    def on_speaker_change(self, *args):
        self.scale.set_sensitive(not config.audio.speaker.muted)
        self.scale.set_value(config.audio.speaker.volume)

        if self.client.speaker.muted:
            self.icon_button.add_style_class("button-basic-active")
            self.icon_button.remove_style_class("button-basic")
        else:
            self.icon_button.remove_style_class("button-basic-active")
            self.icon_button.add_style_class("button-basic")

        icon_name = "-".join(str(self.client.speaker.icon_name).split("-")[0:2])
        if icon_name != self.icon_name:
            self.icon_name = icon_name
            self.icon.set_from_icon_name(icon_name + "-symbolic", 24)
            self.icon.set_pixel_size(self.pixel_size)

    def on_reveal(self, revealer, _):
        # filled while the picker is open, like the mute button while muted
        if revealer.get_reveal_child():
            self.reveal_button.add_style_class(["open", "button-basic-active"])
            self.reveal_button.remove_style_class("button-basic")
        else:
            self.reveal_button.remove_style_class(["open", "button-basic-active"])
            self.reveal_button.add_style_class("button-basic")

    def on_button_click(self, *_):
        self.client.speaker.muted = not self.client.speaker.muted
