import os
import mimetypes
import json

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from gi.repository import GLib

# from fabric_config.widgets.rounded_image import CustomImage
from fabric.widgets.image import Image
from fabric.utils import exec_shell_command_async
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric_config.widgets.popup_window_v2 import PopupWindow
from fabric.core.service import Signal

WALLPAPER_DIR = f"/home/{GLib.get_user_name()}/wallpapers"
WALLPAPER_THUMBS_DIR = f"/home/{GLib.get_user_name()}/wallpapers/.thumbs"
CACHE_DIR = str(GLib.get_user_cache_dir()) + "/fabric"
WALLPAPER_CACHE = CACHE_DIR + "/wallpaper-picker"
LAST_WALLPAPER_FILE = WALLPAPER_CACHE + "/last_selected.json"

if not os.path.exists(WALLPAPER_DIR):
    os.makedirs(WALLPAPER_DIR)

if not os.path.exists(WALLPAPER_THUMBS_DIR):
    os.makedirs(WALLPAPER_THUMBS_DIR)

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

if not os.path.exists(WALLPAPER_CACHE):
    os.makedirs(WALLPAPER_CACHE)


def _save_last_wallpaper(wp_path: str):
    try:
        with open(LAST_WALLPAPER_FILE, "w") as f:
            json.dump({"path": wp_path}, f)
    except Exception:
        return


def _get_last_wallpaper() -> str | None:
    if not os.path.exists(LAST_WALLPAPER_FILE):
        return None

    try:
        with open(LAST_WALLPAPER_FILE, "r") as f:
            data = json.load(f)
            path = data.get("path")
            if path and os.path.exists(path):
                return path
    except Exception:
        return None

    return None


class ImageButton(Button):
    @Signal
    def wallpaper_change(self, wp_path: str) -> str: ...

    def __init__(self, wallpaper_name, thumb_size=300, **kwargs):
        self.wallpaper_name = wallpaper_name
        self.wp_path = os.path.join(WALLPAPER_DIR, self.wallpaper_name)
        self.thumb_size = thumb_size
        self.wp_thumb_path = os.path.join(
            WALLPAPER_THUMBS_DIR, f"{self.thumb_size}_{self.wallpaper_name}"
        )
        super().__init__(
            style_classes=["button-basic", "button-basic-props", "cool-border"],
            on_clicked=lambda *_: self._set_wallpaper_from_image(),
            **kwargs,
        )
        self._generate_wp_thumbnail()

    def _set_wallpaper_from_image(self):
        _save_last_wallpaper(self.wp_path)
        self.wallpaper_change(self.wp_path)

        exec_shell_command_async(
            f"hyprctl hyprpaper wallpaper ', {self.wp_path}'", lambda *_: None
        )

    def _generate_wp_thumbnail(self):
        if os.path.exists(self.wp_thumb_path):
            self.set_image(
                Image(image_file=self.wp_thumb_path, style="border-radius: 20px")
            )
            return

        exec_shell_command_async(
            f"ffmpegthumbnailer -i {self.wp_path} -s {self.thumb_size} -o {self.wp_thumb_path}",
            lambda *_: self.set_image(
                Image(image_file=self.wp_thumb_path, style="border-radius: 20px")
            ),
        )


class WallpaperPickerBox(ScrolledWindow):
    @Signal
    def wallpaper_change(self, wp_path: str) -> str: ...

    def __init__(self, **kwargs):
        self._buttons = []
        super().__init__(
            orientation="h",
            max_content_size=(-1, 800),
            on_destroy=self.destroy_wallpaper_images,
            **kwargs,
        )

    def destroy_wallpaper_images(self, *_):
        [b.destroy() for b in self._buttons]
        [c.destroy() for c in self._main_box.children]
        self._buttons = []
        self._main_box.destroy()

    def grab_wallpaper_images(self, *_):
        if len(self._buttons) == 0:
            self._buttons = self._grab_wallpeper_images()
        else:
            return

        row_size = 3
        rows = [
            self._buttons[i : i + row_size]
            for i in range(0, len(self._buttons), row_size)
        ]
        self._main_box = Box(
            orientation="v",
            children=[Box(children=row, orientation="h", spacing=10) for row in rows],
            spacing=10,
        )
        self.children = self._main_box

    def _grab_wallpeper_images(self) -> list[ImageButton]:
        images = []
        for wp in os.listdir(WALLPAPER_DIR):
            file_type = mimetypes.guess_type(wp)[0]
            if file_type and "image" in file_type:
                images.append(
                    ImageButton(
                        wp,
                        on_wallpaper_change=lambda _, wp_path: self.wallpaper_change(
                            wp_path
                        ),
                    )
                )
        return images


class WallPaperPickerOverlay(PopupWindow):
    def __init__(self):
        self.wallpaper_box = WallpaperPickerBox(
            on_wallpaper_change=lambda *_: self.toggle_popup()
        )
        super().__init__(
            layer="top",
            child=Box(
                orientation="v",
                spacing=10,
                children=[
                    Label(
                        "Wallpaper Picker",
                        style_classes=["label-title"],
                    ),
                    self.wallpaper_box,
                ],
                style_classes=["cool-border", "window-basic"],
            ),
            transition_duration=300,
            transition_type="crossfade",
            anchor="center",
            enable_inhibitor=True,
        )
        self.reveal_child.revealer.connect(
            "notify::child-revealed",
            lambda *_: (
                [
                    self.wallpaper_box.destroy_wallpaper_images(),
                ]
                if not self.reveal_child.revealer.child_revealed
                else None
            ),
        )
        self._apply_last_selected_wallpaper()

    def _apply_last_selected_wallpaper(self):
        last_wallpaper = _get_last_wallpaper()
        if not last_wallpaper:
            return

        exec_shell_command_async(
            f"hyprctl hyprpaper wallpaper ', {last_wallpaper}'",
            lambda *_: None,
        )

    def toggle_popup(self, monitor: bool = False):
        super().toggle_popup(monitor=True)
        if self.popup_visible:
            self.wallpaper_box.grab_wallpaper_images()


wallpaper_picker = WallPaperPickerOverlay()
