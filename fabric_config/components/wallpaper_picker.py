import mimetypes
import os
from collections.abc import Callable

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
from fabric_config.utils.wallpaper import (
    apply_wallpaper,
    list_monitors,
    query_active_wallpapers,
    restore_wallpapers,
    save_wallpaper,
)
from fabric_config.widgets.popup_window_v2 import PopupWindow
from fabric_config.widgets.rounded_cover_image import RoundedCoverImage

WALLPAPER_DIR = os.path.join(GLib.get_home_dir(), "wallpapers")
WALLPAPER_THUMBS_DIR = os.path.join(WALLPAPER_DIR, ".thumbs")
CACHE_DIR = str(GLib.get_user_cache_dir()) + "/fabric"
WALLPAPER_CACHE = CACHE_DIR + "/wallpaper-picker"

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
    """
    A wallpaper thumbnail. Left click sets it on every monitor; right click
    opens a menu to set it on one monitor. Chips name the monitors showing it.
    """

    def __init__(
        self,
        wallpaper_name: str,
        on_set: Callable[[str, list[str] | None], None],
        get_monitors: Callable[[], list[dict]],
        **kwargs,
    ):
        self.wallpaper_name = wallpaper_name
        self.wp_path = os.path.join(WALLPAPER_DIR, wallpaper_name)
        self.wp_thumb_path = os.path.join(
            WALLPAPER_THUMBS_DIR, f"{THUMB_SIZE}_{wallpaper_name}"
        )
        self._on_set = on_set
        self._get_monitors = get_monitors
        self._monitors_using: list[str] = []
        self._menu: Gtk.Menu | None = None
        self.tile = RoundedCoverImage(TILE_WIDTH, TILE_HEIGHT, TILE_RADIUS)

        # chips naming the monitors that currently show this wallpaper
        self.chips = Box(
            name="wallpaper-monitor-chips",
            spacing=4,
            h_align="end",
            v_align="start",
        )
        self.chips.set_no_show_all(True)

        super().__init__(
            name="wallpaper-card",
            tooltip_text=f"{wallpaper_name}\nClick: all monitors · Right-click: choose monitor",
            child=Overlay(child=self.tile, overlays=self.chips),
            on_clicked=lambda *_: self._on_set(self.wp_path, None),
            on_button_press_event=self._on_button_press,
            **kwargs,
        )
        self._load_thumbnail()

    def set_monitors_using(self, monitor_names: list[str]):
        self._monitors_using = monitor_names
        for child in self.chips.get_children():
            child.destroy()
        for name in monitor_names:
            chip = Box(name="wallpaper-monitor-chip", children=Label(label=name))
            chip.show_all()
            self.chips.add(chip)
        self.chips.set_visible(bool(monitor_names))
        if monitor_names:
            self.add_style_class("current")
        else:
            self.remove_style_class("current")

    def _on_button_press(self, _button, event):
        if event.button != 3:
            return False
        self._show_menu(event)
        return True

    def _show_menu(self, event):
        menu = Gtk.Menu()
        menu.get_style_context().add_class("tray")  # shared menu styling
        monitors = self._get_monitors()
        for monitor in monitors:
            name = monitor["name"]
            label = f"{name}  ·  {monitor['width']}×{monitor['height']}"
            if name in self._monitors_using:
                label = "✓  " + label
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _i, n=name: self._on_set(self.wp_path, [n]))
            menu.append(item)
        if len(monitors) > 1:
            menu.append(Gtk.SeparatorMenuItem())
        all_item = Gtk.MenuItem(label="All monitors")
        all_item.connect("activate", lambda _i: self._on_set(self.wp_path, None))
        menu.append(all_item)
        menu.show_all()
        # keep a reference, or the menu is garbage collected while open
        self._menu = menu
        menu.popup_at_pointer(event)

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
    def wallpaper_set(self, all_monitors: bool) -> bool: ...

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
        self._cards: dict[str, WallpaperCard] = {}
        self._monitors: list[dict] = []

    def build(self) -> int:
        """Populate the grid (once until cleared); returns the image count."""
        if self._built:
            return len(self._cards)
        self._built = True
        self._monitors = list_monitors()

        names = _list_wallpapers()
        for name in names:
            card = WallpaperCard(
                name, on_set=self._set_wallpaper, get_monitors=lambda: self._monitors
            )
            self._cards[card.wp_path] = card
            self.flowbox.add(card)
        self.flowbox.show_all()
        self.empty_label.set_visible(not names)
        self.get_vadjustment().set_value(0)
        self.refresh_assignments()
        return len(names)

    def refresh_assignments(self):
        """Ask hyprpaper what each monitor shows and update the chips."""

        def on_active(active: dict[str, str]):
            by_path: dict[str, list[str]] = {}
            # keep monitors in layout order (left to right)
            for monitor in sorted(self._monitors, key=lambda m: (m["x"], m["y"])):
                path = active.get(monitor["name"])
                if path:
                    by_path.setdefault(path, []).append(monitor["name"])
            for path, card in self._cards.items():
                card.set_monitors_using(by_path.get(path, []))

        query_active_wallpapers(on_active)

    def _set_wallpaper(self, path: str, monitor_names: list[str] | None):
        targets = (
            [m["name"] for m in self._monitors]
            if monitor_names is None
            else monitor_names
        )
        save_wallpaper(path, monitor_names)
        apply_wallpaper(path, targets, on_done=self.refresh_assignments)
        self.wallpaper_set(monitor_names is None)

    def clear(self):
        # free the pixbufs while hidden; rebuilt on next open
        for child in self.flowbox.get_children():
            child.destroy()
        self._cards.clear()
        self._built = False


class WallPaperPickerOverlay(PopupWindow):
    def __init__(self):
        # left click (all monitors) closes the picker; setting a single
        # monitor keeps it open so the other monitors can be set next
        self.wallpaper_grid = WallpaperGrid(
            on_wallpaper_set=lambda _grid, all_monitors: (
                self.toggle_popup() if all_monitors else None
            )
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
            end_children=Box(
                spacing=12,
                children=[
                    Label(
                        "Click: all monitors · Right-click: choose monitor",
                        name="wallpaper-picker-hint",
                        v_align="center",
                    ),
                    open_folder_button,
                ],
            ),
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
        # each monitor gets its own saved wallpaper back
        restore_wallpapers()

    def toggle_popup(self, monitor: bool = False):
        super().toggle_popup(monitor=True)
        if self.popup_visible:
            count = self.wallpaper_grid.build()
            folder = WALLPAPER_DIR.replace(GLib.get_home_dir(), "~")
            self.count_label.set_label(
                f"{count} image{'s' if count != 1 else ''} · {folder}"
            )


wallpaper_picker = WallPaperPickerOverlay()
