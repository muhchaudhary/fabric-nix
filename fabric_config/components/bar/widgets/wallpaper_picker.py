from fabric import Fabricator
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image


class WallpapperPickerButton(Button):
    def __init__(self, **kwargs):
        super().__init__(
            image=Image(icon_name="image-x-generic-symbolic"),
            style_classes=["button-basic", "button-basic-props", "button-border"],
            on_clicked=lambda *_: None,
        )
