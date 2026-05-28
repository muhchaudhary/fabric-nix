import fabric_config.config as config
from fabric_config.components.quick_settings.widgets.quick_settings_toggle_button import (
    QuickSettingsToggleButton,
)


class ThemeToggle(QuickSettingsToggleButton):
    def __init__(self, **kwargs):
        super().__init__(
            action_label="Light Mode",
            action_icon="weather-clear-symbolic",
            active=config.theme.is_light,
            on_toggle=self._on_toggled,
            **kwargs,
        )

    def _on_toggled(self, active: bool):
        config.theme.is_light = active
