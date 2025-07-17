import os
import mimetypes

from fabric import Application
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from gi.repository import GLib
from fabric.widgets.wayland import WaylandWindow
from fabric.utils import exec_shell_command_async


# TODO: implement config
WALLPAPER_DIR = f"/home/{GLib.get_user_name()}/wallpapers"


class ImageButton(Button):
    def __init__(self, wp):
        self.wp_path = wp
        super().__init__(
            image=Image(image_file=self.wp_path, size=(200, 200)),
            on_clicked=lambda *_: self._set_wallpaper_from_image(),
        )

    def _set_wallpaper_from_image(self):
        def on_wallpaper_change(*_):
            print("wallpaper changed!")

        exec_shell_command_async(
            f"hyprctl hyprpaper reload ,'{self.wp_path}'", on_wallpaper_change
        )
        


class WallpaperPicker(Box):
    def __init__(self, **kwargs):
        super().__init__(orientation="v", size=(500, 500))
        self._wallpapers = []
        self._buttons = self._grab_wallpeper_images()
        self.children = self._buttons

    def _grab_wallpeper_images(self) -> list[ImageButton]:
        images = []
        for wp in os.listdir(WALLPAPER_DIR):
            file_type = mimetypes.guess_type(wp)[0]
            if file_type and "image" in file_type:
                images.append(ImageButton(f"{WALLPAPER_DIR}/{wp}"))
        return images


win = WaylandWindow(layer="overlay", anchor="center", child=WallpaperPicker())

app = Application()

app.run()
