from components.quick_settings.widgets.quick_settings_scale import QuickSettingsScale
from services.brightness import Brightness


class BrightnessSlider(QuickSettingsScale):
    def __init__(
        self,
        client: Brightness,
        **kwargs,
    ):
        self.client = client
        super().__init__(
            min=0,
            max=client.max_screen,
            start_value=client.screen_brightness,
            icon_name="display-brightness-symbolic",
            **kwargs,
        )

        self.scale.connect("change-value", self.on_scale_move)
        self.client.connect("screen", self.on_brightness_change)
        if self.client.screen_brightness == -1:
            self.destroy()

    def on_scale_move(self, _, __, moved_pos):
        # TODO switch to getters and setters
        self.client.screen_brightness = moved_pos

    def on_brightness_change(self, *_):
        self.scale.set_value(self.client.screen_brightness)
