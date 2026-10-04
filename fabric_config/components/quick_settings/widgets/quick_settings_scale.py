from fabric.widgets.scale import Scale
from fabric.widgets.box import Box
from fabric.widgets.image import Image
from fabric.widgets.button import Button
from fabric.widgets.label import Label


class QuickSettingsScale(Box):
    def __init__(
        self,
        min: float = 0,
        max: float = 100,
        start_value: float = 50,
        icon_name: str = "package-x-generic-symbolic",
        pixel_size: int = 28,
        **kwargs,
    ):
        self.pixel_size = pixel_size
        self.icon = Image(icon_name=icon_name, icon_size=self.pixel_size)
        self.icon_button = Button(
            image=self.icon,
            style_classes=["button-basic", "button-basic-props", "button-border"],
        )

        self.scale = Scale(
            min_value=min,
            max_value=max,
            name="quicksettings-slider",
            value=start_value,
            h_expand=True,
        )

        # the value as a percentage, following the slider
        self.percent = Label(
            "", name="quicksettings-slider-value", style_classes=["tnum"]
        )
        self.scale.connect("value-changed", lambda *_: self._update_percent())
        self._update_percent()

        # the icon, scale and value; subclasses can add buttons after them
        self.row = Box(
            spacing=5,
            children=[self.icon_button, self.scale, self.percent],
            h_expand=True,
        )

        super().__init__(
            name="quicksettings-box",
            style_classes=["cool-border"],
            children=self.row,
            **kwargs,
        )

    def _update_percent(self):
        adjustment = self.scale.get_adjustment()
        span = adjustment.get_upper() - adjustment.get_lower()
        value = (self.scale.get_value() - adjustment.get_lower()) / span if span else 0
        self.percent.set_label(f"{round(value * 100)}%")
