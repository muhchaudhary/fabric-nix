from fabric_config.components.quick_settings.widgets.quick_settings_scale import (
    QuickSettingsScale,
)
from fabric_config.services.brightness import Brightness


class BrightnessSlider(QuickSettingsScale):
    def __init__(
        self,
        client: Brightness,
    ):
        self.client = client
        super().__init__(
            min=0,
            max=client.max_screen if client.max_screen != -1 else 0,
            start_value=client.screen_brightness,
            icon_name="display-brightness-symbolic",
        )

        if self.client.screen_brightness == -1:
            self.destroy()
            return

        if self.scale:
            self.scale.connect("change-value", self.on_scale_move)
            self.client.connect("notify::screen-brightness", self.on_brightness_change)

    def on_scale_move(self, _, __, moved_pos):
        # TODO switch to getters and setters
        self.client.screen_brightness = moved_pos

    def on_brightness_change(self, service: Brightness, _):
        self.scale.set_value(service.screen_brightness)
