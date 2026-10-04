from fabric.widgets.box import Box
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scale import Scale

from fabric_config.components.quick_settings.widgets.quick_settings_submenu import (
    QuickSubMenu,
    QuickSubToggle,
)
from fabric_config.services.hyprsunset import (
    MAX_GAMMA,
    MAX_TEMPERATURE,
    MIN_GAMMA,
    MIN_TEMPERATURE,
    Hyprsunset,
)
from fabric_config.widgets.toggle_pill import ToggleSwitch


def _mirror(temperature: float) -> float:
    """Temperature <-> slider position: warmer (lower K) is further right."""
    return MIN_TEMPERATURE + MAX_TEMPERATURE - temperature


class NightLightScale(Box):
    """A labelled slider row: icon, name and value above the scale."""

    def __init__(
        self,
        label: str,
        icon_name: str,
        min_value: int,
        max_value: int,
        unit: str,
        **kwargs,
    ):
        self.unit = unit
        self.value_label = Label(
            style_classes=["submenu-card-sublabel"], h_align="end", h_expand=True
        )
        self.scale = Scale(
            min_value=min_value,
            max_value=max_value,
            increments=(100, 500) if unit == "K" else (5, 10),
            name="quicksettings-slider",
            h_expand=True,
        )
        super().__init__(
            orientation="v",
            style_classes=["submenu-card"],
            children=[
                Box(
                    spacing=8,
                    children=[
                        Image(
                            icon_name=icon_name,
                            icon_size=16,
                            style_classes=["submenu-card-icon"],
                        ),
                        Label(label=label, style_classes=["submenu-card-label"]),
                        self.value_label,
                    ],
                ),
                self.scale,
            ],
            **kwargs,
        )

    def set_value(self, value: float, label: int):
        self.scale.set_value(value)
        self.value_label.set_label(f"{label}{self.unit}")


class NightLightSubMenu(QuickSubMenu):
    def __init__(self, client: Hyprsunset, **kwargs):
        self.client = client

        self.switch = ToggleSwitch(
            active=client.enabled,
            on_toggled=lambda active: setattr(client, "enabled", active),
        )
        self.temperature = NightLightScale(
            "Warmth",
            "weather-clear-night-symbolic",
            MIN_TEMPERATURE,
            MAX_TEMPERATURE,
            "K",
        )
        self.gamma = NightLightScale(
            "Gamma", "display-brightness-symbolic", MIN_GAMMA, MAX_GAMMA, "%"
        )
        self.temperature.scale.connect("change-value", self.on_temperature_move)
        self.gamma.scale.connect("change-value", self.on_gamma_move)

        super().__init__(
            title="Night Light",
            title_icon="night-light-symbolic",
            title_action=self.switch,
            child=Box(
                orientation="v",
                spacing=2,
                children=[self.temperature, self.gamma],
            ),
            **kwargs,
        )

        client.connect("notify::enabled", self.sync)
        client.connect("notify::temperature", self.sync)
        client.connect("notify::gamma", self.sync)
        self.sync()

    def sync(self, *_):
        if self.switch.get_active() != self.client.enabled:
            self.switch.set_active(self.client.enabled)
        temperature = self.client.temperature
        self.temperature.set_value(_mirror(temperature), temperature)
        self.gamma.set_value(self.client.gamma, self.client.gamma)

    def on_temperature_move(self, _scale, _scroll, value: float):
        # adjusting the warmth turns the filter on, so the change shows
        self.client.temperature = round(_mirror(value) / 100) * 100
        self.client.enabled = True

    def on_gamma_move(self, _scale, _scroll, value: float):
        self.client.gamma = round(value)
        self.client.enabled = True


class NightLightToggle(QuickSubToggle):
    def __init__(self, submenu: QuickSubMenu, client: Hyprsunset, **kwargs):
        super().__init__(
            action_icon="night-light-symbolic",
            action_label="Off",
            title="Night Light",
            submenu=submenu,
            **kwargs,
        )
        self.client = client
        self.connect("action-clicked", lambda *_: client.toggle())
        client.connect("notify::enabled", self.update_action_button)
        client.connect("notify::available", self.update_action_button)
        client.connect("notify::temperature", self.update_action_button)
        self.update_action_button()

    def update_action_button(self, *_):
        self.set_active_style(self.client.enabled)
        if not self.client.available:
            self.action_label.set_label("Unavailable")
        else:
            self.action_label.set_label(
                f"{self.client.temperature} K" if self.client.enabled else "Off"
            )
        self.set_action_icon(
            "night-light-symbolic"
            if self.client.enabled
            else "night-light-disabled-symbolic"
        )
        self.set_tooltip_text(
            None if self.client.available else "hyprsunset isn't running"
        )
