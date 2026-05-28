from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label

import fabric_config.config as config
from fabric_config.widgets.toggle_pill import ToggleSwitch


class ThemeToggle(CenterBox):
    def __init__(self, **kwargs):
        self._switch = ToggleSwitch(
            active=config.theme.is_light,
            on_toggled=self._on_toggled,
        )

        super().__init__(
            h_expand=True,
            style_classes=["submenu-card"],
            start_children=[
                Box(
                    spacing=10,
                    v_align="center",
                    children=[
                        Image(
                            icon_name="weather-clear-symbolic",
                            icon_size=16,
                            style_classes=["submenu-card-icon"],
                        ),
                        Label(
                            label="Light Mode",
                            style_classes=["submenu-card-label"],
                        ),
                    ],
                )
            ],
            end_children=[self._switch],
            **kwargs,
        )

    def _on_toggled(self, active: bool):
        config.theme.is_light = active
