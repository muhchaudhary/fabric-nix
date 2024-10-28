from fabric.widgets.scale import Scale
from fabric.widgets.box import Box
from fabric.widgets.image import Image
from fabric.widgets.button import Button


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
        self.icon_button = Button(image=self.icon, name="panel-button")

        self.scale = Scale(
            min_value=min,
            max_value=max,
            name="quicksettings-slider",
            value=start_value,
            h_expand=True,
        )

        super().__init__(
            name="quicksettings-box",
            children=Box(
                spacing=5, children=[self.icon_button, self.scale], h_expand=True
            ),
            **kwargs,
        )
