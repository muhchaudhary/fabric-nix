from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric_config.components.wallpaper_picker import wallpaper_picker


class WallpapperPickerButton(Button):
    def __init__(self, **kwargs):
        super().__init__(
            image=Image(icon_name="image-x-generic-symbolic"),
            style_classes=["button-basic", "button-basic-props", "button-border"],
            on_clicked=lambda *_: wallpaper_picker.toggle_popup(),
        )
