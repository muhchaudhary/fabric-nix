"""
Dominant colours of the current wallpapers, and the theme accent made from
them.

`colors` maps each monitor to its wallpaper's dominant colour (the desktop
clock tints itself per monitor from it). `accent` is the one colour the whole
theme uses: the wallpaper shared by every monitor, or else the largest
monitor's. `apply_to_theme()` overrides the stylesheet's `@accent` with a
version of it tuned for the light or dark palette.
"""

import colorsys

from fabric.core.service import Property, Service, Signal
from fabric.utils import monitor_file
from gi.repository import Gdk, GLib, Gtk

from fabric_config.utils.accent import grab_dominant_color_threaded
from fabric_config.utils.wallpaper import (
    LAST_WALLPAPER_FILE,
    list_monitors,
    query_active_wallpapers,
    wallpaper_for_monitor,
)

RGB = tuple[int, int, int]

# one save fires several file events, and hyprpaper switches a moment after
# the picker saves: wait for the burst to settle, then update once
DEBOUNCE_MS = 500
# startup scripts may set the wallpaper without going through the picker
STARTUP_DELAY_MS = 1500


def theme_accent_rgb(rgb: RGB, is_light: bool) -> tuple[float, float, float]:
    """
    The wallpaper colour as a usable accent, as 0-1 floats: light enough to
    read on the dark palette (dark enough on the light one) and never so grey
    it disappears.
    """
    h, _light, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    return colorsys.hls_to_rgb(h, 0.42 if is_light else 0.72, min(max(s, 0.3), 0.65))


def theme_accent(rgb: RGB, is_light: bool) -> str:
    r, g, b = theme_accent_rgb(rgb, is_light)
    return f"rgb({round(r * 255)},{round(g * 255)},{round(b * 255)})"


class WallpaperAccent(Service):
    @Signal
    def changed(self) -> None: ...

    @Property(object, "readable")
    def colors(self) -> dict[str, RGB]:
        return self._colors

    @Property(object, "readable")
    def accent(self) -> RGB | None:
        return self._accent

    def accent_rgb(self) -> RGB | None:
        """The theme accent's source colour, once known (typed `accent`)."""
        return self._accent

    def color_for(self, monitor_name: str) -> RGB | None:
        """Dominant colour of that monitor's wallpaper, once known."""
        return self._colors.get(monitor_name)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._colors: dict[str, RGB] = {}
        self._accent: RGB | None = None
        self._cache: dict[str, RGB | None] = {}
        # callbacks waiting on an extraction already running for that path
        self._waiting: dict[str, list] = {}
        self._timer: int | None = None
        self._provider: Gtk.CssProvider | None = None

        self._file_monitor = monitor_file(LAST_WALLPAPER_FILE)
        self._file_monitor.connect("changed", lambda *_: self.update_soon())
        GLib.timeout_add(STARTUP_DELAY_MS, lambda: self.update() or False)

    def update_soon(self):
        if self._timer is not None:
            GLib.source_remove(self._timer)

        def fire():
            self._timer = None
            self.update()
            return False

        self._timer = GLib.timeout_add(DEBOUNCE_MS, fire)

    def update(self):
        def on_active(active: dict[str, str]):
            monitors = list_monitors()
            names = [m["name"] for m in monitors] or list(active)
            paths = {
                name: path
                for name in names
                if (path := active.get(name) or wallpaper_for_monitor(name))
            }
            if not paths:
                return
            self._resolve(paths, monitors)

        query_active_wallpapers(on_active)

    def _resolve(self, paths: dict[str, str], monitors: list[dict]):
        pending = {p for p in paths.values() if p not in self._cache}

        def finish():
            self._colors = {
                name: color
                for name, path in paths.items()
                if (color := self._cache.get(path))
            }
            self._accent = self._colors.get(self._primary(paths, monitors))
            self.notify("colors")
            self.notify("accent")
            self.changed()

        if not pending:
            finish()
            return

        def on_ready(path: str):
            pending.discard(path)
            if not pending:
                finish()

        for path in list(pending):
            if path in self._waiting:
                # same wallpaper already being read: wait for that result
                self._waiting[path].append(on_ready)
                continue
            self._waiting[path] = [on_ready]

            def on_color(rgb, path=path):
                self._cache[path] = (rgb[0], rgb[1], rgb[2]) if rgb else None
                for callback in self._waiting.pop(path, []):
                    callback(path)
                return False

            grab_dominant_color_threaded(path, on_color)

    @staticmethod
    def _primary(paths: dict[str, str], monitors: list[dict]) -> str:
        if len(set(paths.values())) == 1:
            return next(iter(paths))
        sizes = {m["name"]: m.get("width", 0) * m.get("height", 0) for m in monitors}
        return max(paths, key=lambda name: sizes.get(name, 0))

    def apply_to_theme(self, is_light: bool):
        """Override the stylesheet's @accent (or restore it when unknown)."""
        screen = Gdk.Screen.get_default()
        if screen is None:
            return
        if self._provider is not None:
            Gtk.StyleContext.remove_provider_for_screen(screen, self._provider)
            self._provider = None
        if self._accent is None:
            return
        self._provider = Gtk.CssProvider()
        self._provider.load_from_data(
            f"@define-color accent {theme_accent(self._accent, is_light)};".encode()
        )
        # GTK resolves named colours from the highest-priority provider that
        # defines them, so this beats the palette's own @define-color
        Gtk.StyleContext.add_provider_for_screen(
            screen, self._provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 5
        )
