import json
import mimetypes
import os
import subprocess

from fabric.core.service import Signal
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.scrolledwindow import ScrolledWindow
from gi.repository import GdkPixbuf, Gio, GLib, Gtk
from loguru import logger

from fabric_config.utils.process import run_command_async
from fabric_config.widgets.popup_window_v2 import PopupWindow
from fabric_config.widgets.rounded_cover_image import RoundedCoverImage

WALLPAPER_DIR = os.path.join(GLib.get_home_dir(), "wallpapers")
WALLPAPER_THUMBS_DIR = os.path.join(WALLPAPER_DIR, ".thumbs")
CACHE_DIR = str(GLib.get_user_cache_dir()) + "/fabric"
WALLPAPER_CACHE = CACHE_DIR + "/wallpaper-picker"
LAST_WALLPAPER_FILE = WALLPAPER_CACHE + "/last_selected.json"

THUMB_SIZE = 480  # px wide; tiles are drawn at up to 2x, so this stays sharp
TILE_WIDTH = 256
TILE_HEIGHT = 144  # 16:9
TILE_RADIUS = 12
GRID_COLUMNS = 3

if not os.path.exists(WALLPAPER_DIR):
    os.makedirs(WALLPAPER_DIR)

if not os.path.exists(WALLPAPER_THUMBS_DIR):
    os.makedirs(WALLPAPER_THUMBS_DIR)

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

if not os.path.exists(WALLPAPER_CACHE):
    os.makedirs(WALLPAPER_CACHE)


def _set_hyprpaper_wallpaper(wp_path: str):
    try:
        monitors = json.loads(subprocess.check_output(["hyprctl", "-j", "monitors"]))
        for monitor in monitors:
            run_command_async(
                ["hyprctl", "hyprpaper", "wallpaper", f"{monitor['name']},{wp_path}"]
            )
    except Exception:
        pass


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


def _load_pixbuf_async(path: str, callback):
    """Load an image file without blocking the main loop."""

    def on_pixbuf(_source, result: Gio.AsyncResult):
        try:
            callback(GdkPixbuf.Pixbuf.new_from_stream_finish(result))
        except GLib.Error as e:
            logger.error(f"[Wallpaper] Failed to load {path}: {e.message}")

    def on_read(file: Gio.File, result: Gio.AsyncResult):
        try:
            stream = file.read_finish(result)
        except GLib.Error as e:
            logger.error(f"[Wallpaper] Failed to open {path}: {e.message}")
            return
        GdkPixbuf.Pixbuf.new_from_stream_async(stream, None, on_pixbuf)

    Gio.File.new_for_path(path).read_async(GLib.PRIORITY_DEFAULT, None, on_read)


def _list_wallpapers() -> list[str]:
    names = []
    for name in os.listdir(WALLPAPER_DIR):
        file_type = mimetypes.guess_type(name)[0]
        if file_type and file_type.startswith("image/"):
            names.append(name)
    return sorted(names, key=str.lower)


class WallpaperCard(Button):
    @Signal
    def wallpaper_change(self, wp_path: str) -> str: ...

    def __init__(self, wallpaper_name: str, is_current: bool = False, **kwargs):
        self.wallpaper_name = wallpaper_name
        self.wp_path = os.path.join(WALLPAPER_DIR, wallpaper_name)
        self.wp_thumb_path = os.path.join(
            WALLPAPER_THUMBS_DIR, f"{THUMB_SIZE}_{wallpaper_name}"
        )
        self.tile = RoundedCoverImage(TILE_WIDTH, TILE_HEIGHT, TILE_RADIUS)

        badge = Box(
            name="wallpaper-current-badge",
            h_align="end",
            v_align="start",
            children=Image(icon_name="object-select-symbolic", icon_size=14),
        )
        # keep the grid's show_all() from revealing the badge on every card
        badge.set_no_show_all(True)
        badge.set_visible(is_current)

        super().__init__(
            name="wallpaper-card",
            tooltip_text=wallpaper_name,
            child=Overlay(child=self.tile, overlays=badge),
            on_clicked=lambda *_: self._set_wallpaper_from_image(),
            **kwargs,
        )
        if is_current:
            self.add_style_class("current")
        self._load_thumbnail()

    def _set_wallpaper_from_image(self):
        _save_last_wallpaper(self.wp_path)
        self.wallpaper_change(self.wp_path)
        _set_hyprpaper_wallpaper(self.wp_path)

    def _load_thumbnail(self):
        if os.path.exists(self.wp_thumb_path):
            _load_pixbuf_async(self.wp_thumb_path, self.tile.set_pixbuf)
            return

        def on_thumbnail_done(success: bool, _stdout: str, stderr: str):
            if not success:
                logger.error(
                    f"[Wallpaper] Failed to thumbnail {self.wp_path}: {stderr.strip()}"
                )
                return
            _load_pixbuf_async(self.wp_thumb_path, self.tile.set_pixbuf)

        # argv list rather than a shell string, so file names with spaces work;
        # the callback fires on exit, since ffmpegthumbnailer prints nothing
        run_command_async(
            [
                "ffmpegthumbnailer",
                "-i",
                self.wp_path,
                "-s",
                str(THUMB_SIZE),
                "-o",
                self.wp_thumb_path,
            ],
            on_thumbnail_done,
        )


class WallpaperGrid(ScrolledWindow):
    @Signal
    def wallpaper_change(self, wp_path: str) -> str: ...

    def __init__(self, **kwargs):
        self.flowbox = Gtk.FlowBox(
            homogeneous=True,
            selection_mode=Gtk.SelectionMode.NONE,
            min_children_per_line=GRID_COLUMNS,
            max_children_per_line=GRID_COLUMNS,
            row_spacing=6,
            column_spacing=6,
            valign=Gtk.Align.START,
        )
        self.flowbox.set_name("wallpaper-grid")
        self.flowbox.show()
        self.empty_label = Label(
            label=f"No images in {WALLPAPER_DIR.replace(GLib.get_home_dir(), '~')}",
            name="wallpaper-empty",
            visible=False,
        )
        super().__init__(
            name="wallpaper-scroll",
            h_scrollbar_policy="never",
            min_content_size=(-1, 560),
            max_content_size=(-1, 560),
            child=Box(orientation="v", children=[self.flowbox, self.empty_label]),
            **kwargs,
        )
        self._built = False

    def build(self) -> int:
        """Populate the grid (once until cleared); returns the image count."""
        if self._built:
            return len(self.flowbox.get_children())
        self._built = True

        current = _get_last_wallpaper()
        names = _list_wallpapers()
        for name in names:
            card = WallpaperCard(
                name,
                is_current=os.path.join(WALLPAPER_DIR, name) == current,
                on_wallpaper_change=lambda _, wp_path: self.wallpaper_change(wp_path),
            )
            self.flowbox.add(card)
        self.flowbox.show_all()
        self.empty_label.set_visible(not names)
        self.get_vadjustment().set_value(0)
        return len(names)

    def clear(self):
        # free the pixbufs while hidden; rebuilt on next open
        for child in self.flowbox.get_children():
            child.destroy()
        self._built = False


class WallPaperPickerOverlay(PopupWindow):
    def __init__(self):
        self.wallpaper_grid = WallpaperGrid(
            on_wallpaper_change=lambda *_: self.toggle_popup()
        )
        self.count_label = Label(name="wallpaper-picker-subtitle", h_align="start")
        open_folder_button = Button(
            name="wallpaper-picker-folder",
            tooltip_text="Open wallpaper folder",
            image=Image(icon_name="folder-open-symbolic", icon_size=16),
            v_align="center",
            on_clicked=lambda *_: (
                run_command_async(["xdg-open", WALLPAPER_DIR]),
                self.toggle_popup(),
            ),
        )
        header = CenterBox(
            name="wallpaper-picker-header",
            start_children=Box(
                orientation="v",
                children=[
                    Label(
                        "Wallpapers",
                        name="wallpaper-picker-title",
                        h_align="start",
                    ),
                    self.count_label,
                ],
            ),
            end_children=open_folder_button,
        )
        super().__init__(
            layer="top",
            child=Box(
                name="wallpaper-picker",
                orientation="v",
                spacing=12,
                children=[header, self.wallpaper_grid],
            ),
            transition_duration=250,
            transition_type="crossfade",
            anchor="center",
            enable_inhibitor=True,
        )
        self.reveal_child.revealer.connect(
            "notify::child-revealed",
            lambda *_: (
                self.wallpaper_grid.clear()
                if not self.reveal_child.revealer.child_revealed
                else None
            ),
        )
        self._apply_last_selected_wallpaper()

    def _apply_last_selected_wallpaper(self):
        last_wallpaper = _get_last_wallpaper()
        if not last_wallpaper:
            return
        _set_hyprpaper_wallpaper(last_wallpaper)

    def toggle_popup(self, monitor: bool = False):
        super().toggle_popup(monitor=True)
        if self.popup_visible:
            count = self.wallpaper_grid.build()
            folder = WALLPAPER_DIR.replace(GLib.get_home_dir(), "~")
            self.count_label.set_label(
                f"{count} image{'s' if count != 1 else ''} · {folder}"
            )


wallpaper_picker = WallPaperPickerOverlay()
