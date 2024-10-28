from components.quick_settings.widgets.quick_settings_scale import QuickSettingsScale
from fabric.audio.service import Audio
import config


class AudioSlider(QuickSettingsScale):
    def __init__(self, client: Audio):
        self.client = client
        self.icon_name = ""
        super().__init__(min=0, max=100, pixel_size=28)
        self.scale.connect("change-value", self.on_scale_move)
        self.client.connect("speaker-changed", self.on_speaker_change)
        self.icon_button.connect("clicked", self.on_button_click)

    def on_scale_move(self, _, __, moved_pos):
        self.client.speaker.volume = moved_pos

    def on_speaker_change(self, *args):
        self.scale.set_sensitive(not config.audio.speaker.muted)
        self.scale.set_value(config.audio.speaker.volume)
        # TODO use class instead of name here
        self.icon_button.set_name(
            "panel-button-active",
        ) if self.client.speaker.muted else self.icon_button.set_name(
            "panel-button",
        )
        icon_name = "-".join(str(self.client.speaker.icon_name).split("-")[0:2])
        if icon_name != self.icon_name:
            self.icon_name = icon_name
            self.icon.set_from_icon_name(icon_name + "-symbolic", 24)
            self.icon.set_pixel_size(self.pixel_size)

    def on_button_click(self, *_):
        self.client.speaker.muted = not self.client.speaker.muted
