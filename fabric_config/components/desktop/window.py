"""
The desktop: one full-screen window per monitor on the bottom layer (behind
windows, above the wallpaper). It stacks, from the bottom up:

- the drawn layer (prayer arc, audio visualizer),
- sticky notes,
- the clock with its information lines.

Right-click anywhere on it for the menu that switches each piece on or off,
picks the clock face and position, and adds notes. Sizes follow each
monitor's height, so screens of different resolutions look alike.
"""

import colorsys
import datetime
import math
import warnings
from collections.abc import Callable
from dataclasses import dataclass

from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.wayland import WaylandWindow
from gi.repository import Gdk, GLib, Gtk

import fabric_config.config as config
from fabric_config.components.desktop.faces import AnalogFace, DigitalFace, WordFace
from fabric_config.components.desktop.focus import FocusTimer
from fabric_config.components.desktop.fx import FxLayer
from fabric_config.components.desktop.media import get_media_state
from fabric_config.components.desktop.info import (
    OnThisDay,
    WeatherService,
    greeting,
    hijri_date,
)
from fabric_config.components.desktop.notes import NotesLayer, NotesStore
from fabric_config.components.desktop.music_player import MusicPlayerWindow
from fabric_config.components.desktop.settings import (
    FACES,
    PLAYER_SIZES,
    POSITIONS,
    WIDGETS,
    DesktopSettings,
)
from fabric_config.components.desktop.visibility import DesktopVisibility
from fabric_config.utils.process import run_command_async
from fabric_config.utils.wallpaper_map import (
    RegionStats,
    WallpaperMap,
    build_map_async,
    contrast_ratio,
)

SCALE = 1.0  # grows or shrinks the clock on every monitor
GREETING_MS = 5000
# only greet after the desktop has been covered for a while
GREET_AFTER_HIDDEN_S = 120
MOOD_MINUTES = 20

RGB = tuple[int, int, int]

# Legibility. Brightness (0-1, gamma-encoded) of the clock's light and dark
# text, for contrast against what's behind it.
LIGHT_TEXT, DARK_TEXT = 0.93, 0.18
# Behind the clock: more detail than this (std. dev. of brightness), or less
# contrast than this, and a soft scrim (fx.py) is drawn behind it, stronger
# the worse it is. (The desktop layer isn't blurred by Hyprland, which would
# frost the scrim into a hard-edged shape.)
BUSY_LIMIT = 0.1
MIN_CONTRAST = 4.5
SCRIM_MIN_ALPHA, SCRIM_MAX_ALPHA = 0.18, 0.5
# "auto" placement: how much a spot's distance from the classic top-centre
# place counts against it, and how much better a new spot must score before
# the clock moves (so it doesn't wander as its text changes width)
HOME_WEIGHT = 0.06
MOVE_MARGIN = 0.02
LAYOUT_DELAY_MS = 150


def text_contrast(stats: RegionStats) -> tuple[bool, float]:
    """Whether dark text reads better there than light, and its contrast."""
    light = contrast_ratio(LIGHT_TEXT, stats.mean)
    dark = contrast_ratio(DARK_TEXT, stats.mean)
    return dark > light, max(light, dark)


@dataclass(frozen=True)
class ClockSizes:
    """Pixel sizes for one monitor, all derived from its height."""

    time: int
    date: int
    info: int
    memory: int
    words: int
    analog: int
    margin: int

    @classmethod
    def for_height(cls, height: int) -> "ClockSizes":
        time = round(height * 0.2 * SCALE)
        return cls(
            time=time,
            date=round(time * 0.17),
            info=round(time * 0.105),
            memory=round(time * 0.085),
            words=round(height * 0.04 * SCALE),
            analog=round(height * 0.32 * SCALE),
            margin=round(height * 0.06),
        )


def _sizes_css(cls: str, sizes: ClockSizes) -> str:
    """Per-monitor size rules, scoped by the window's class."""
    root = f"#desktop-clock.{cls}"
    # Inter Display's line box is taller than its digits; pull the lines
    # around it in close, like the macOS lock screen
    return f"""
{root} #clock-time {{
  font-size: {sizes.time}px;
  letter-spacing: -{round(sizes.time * 0.025)}px;
  margin-top: -{round(sizes.time * 0.12)}px;
  margin-bottom: -{round(sizes.time * 0.14)}px;
}}
{root} .clock-date {{ font-size: {sizes.date}px; }}
{root} .clock-info {{ font-size: {sizes.info}px; }}
{root} #clock-memory {{ font-size: {sizes.memory}px; }}
{root} #clock-words .clock-word {{ font-size: {sizes.words}px; }}
"""


def readable_accent(rgb: RGB, on_light: bool | None = None) -> tuple[RGB, bool]:
    """
    A tint of a wallpaper's dominant colour for the clock, and whether it is
    dark text (for a light background): near-white with a hint of colour, or
    near-black. Without `on_light`, it's guessed from the colour itself; the
    region actually behind the clock is a better guide (see text_contrast).
    """
    red, green, blue = (c / 255 for c in rgb)
    if on_light is None:
        on_light = 0.2126 * red + 0.7152 * green + 0.0722 * blue > 0.55
    h, _light, s = colorsys.rgb_to_hls(red, green, blue)
    r, g, b = colorsys.hls_to_rgb(h, 0.2 if on_light else 0.93, min(s, 0.4))
    return (round(r * 255), round(g * 255), round(b * 255)), on_light


def _blend(a: RGB, b: RGB, amount: float) -> RGB:
    return (
        round(a[0] + (b[0] - a[0]) * amount),
        round(a[1] + (b[1] - a[1]) * amount),
        round(a[2] + (b[2] - a[2]) * amount),
    )


def _minutes(hhmm: str) -> int | None:
    try:
        hours, minutes = hhmm.split(":")[:2]
        return int(hours) * 60 + int(minutes)
    except (ValueError, AttributeError):
        return None


# moods: a colour the clock drifts toward just after these moments
_MOODS: dict[str, RGB] = {
    "Fajr": (170, 200, 255),  # dawn blue
    "Maghrib": (255, 175, 115),  # sunset amber
    "midnight": (200, 175, 255),  # violet
}


def mood_color(now: datetime.datetime, prayer_times: dict[str, str]) -> RGB | None:
    minute = now.hour * 60 + now.minute
    if minute < MOOD_MINUTES:
        return _MOODS["midnight"]
    for name in ("Fajr", "Maghrib"):
        start = _minutes(prayer_times.get(name, ""))
        if start is not None and 0 <= minute - start < MOOD_MINUTES:
            return _MOODS[name]
    return None


def _prayer_service():
    from fabric_config.components.bar.widgets.prayer_times import (
        _get_prayer_service,
    )

    return _get_prayer_service()


def _scroll_step(event: Gdk.EventScroll) -> int:
    match event.direction:
        case Gdk.ScrollDirection.UP:
            return -1
        case Gdk.ScrollDirection.DOWN:
            return 1
        case Gdk.ScrollDirection.SMOOTH:
            return 1 if event.delta_y > 0 else -1 if event.delta_y < 0 else 0
    return 0


class DesktopWindow(WaylandWindow):
    def __init__(
        self,
        manager: "DesktopManager",
        monitor: int,
        monitor_name: str,
        monitor_height: int,
    ):
        self.manager = manager
        self.monitor_index = monitor
        self.monitor_name = monitor_name
        self.sizes = ClockSizes.for_height(monitor_height)
        self.accent: RGB | None = None
        self.on_light = False
        self._greeting_id: int | None = None
        # the wallpaper behind this monitor's desktop, measured (wallpaper_map)
        self._accent_source: RGB | None = None
        self.wall_map: WallpaperMap | None = None
        self._map_path: str | None = None
        # where "auto" placed the clock (monitor coordinates), and its score
        self._auto_spot: tuple[float, float] | None = None
        self._layout_id: int | None = None
        self._last_rect: tuple[int, int, int, int] | None = None

        # a screen-wide provider whose rules only match this monitor's clock;
        # above the app stylesheet, since GTK picks between providers by
        # priority, not selector specificity
        size_class = "clock-" + "".join(c if c.isalnum() else "-" for c in monitor_name)
        self._size_provider = Gtk.CssProvider()
        self._size_provider.load_from_data(_sizes_css(size_class, self.sizes).encode())
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen, self._size_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 10
            )

        # drawn layer, which also catches right-clicks on the bare desktop
        self.fx = FxLayer(manager.cava)
        self.background = EventBox(
            events=["button-press"], child=self.fx, h_expand=True, v_expand=True
        )
        self.background.connect("button-press-event", self._on_background_press)
        self.fx.connect("size-allocate", lambda *_: self.update_fx())

        # Each piece is its own overlay child covering only its own area, so
        # it gets clicks directly and the bare desktop still reaches the
        # background. (Full-screen click-through layers also pass through
        # the clicks meant for their children.)
        self.overlay = Gtk.Overlay()
        self.overlay.add(self.background)

        self.notes = NotesLayer(manager.notes, monitor_name, self.overlay)

        # clock
        self.digital = DigitalFace(manager.focus.toggle, self.show_menu)
        self.words = WordFace()
        self.faces: dict[str, Gtk.Widget] = {
            "digital": self.digital,
            "analog": AnalogFace(self.sizes.analog),
            "words": self.words,
        }
        self.face_stack = Stack(
            transition_type="crossfade",
            transition_duration=250,
            children=list(self.faces.values()),
        )
        for name, face in self.faces.items():
            self.face_stack.child_set_property(face, "name", name)
        # size to the visible face, not the tallest one
        self.face_stack.set_homogeneous(False)
        self.face_stack.set_interpolate_size(True)
        face_events = EventBox(
            events=["scroll", "smooth-scroll", "button-press"], child=self.face_stack
        )
        face_events.connect("scroll-event", self._on_face_scroll)
        face_events.connect("button-press-event", self._on_background_press)

        self.date_label = Label(style_classes=["clock-date"])
        self.greeting_label = Label(style_classes=["clock-date"])
        self.date_stack = Stack(
            transition_type="crossfade",
            transition_duration=600,
            children=[self.date_label, self.greeting_label],
        )
        self.date_stack.child_set_property(self.date_label, "name", "date")
        self.date_stack.child_set_property(self.greeting_label, "name", "greeting")

        self.prayer_label = Label(name="clock-prayer", style_classes=["clock-info"])
        self.meta_label = Label(name="clock-meta", style_classes=["clock-info"])
        self.memory_label = Label(
            name="clock-memory", max_chars_width=70, ellipsization="end"
        )
        self.memory = EventBox(
            events=["button-press"],
            child=self.memory_label,
            h_align="center",
            style_classes=["clickable"],
        )
        self.memory.connect("button-press-event", self._on_memory_press)

        self.column = Box(
            name="desktop-clock",
            style_classes=[size_class],
            orientation="v",
            children=[
                self.date_stack,
                face_events,
                Box(
                    name="clock-lines",
                    orientation="v",
                    spacing=4,
                    children=[
                        self.prayer_label,
                        self.meta_label,
                        self.memory,
                    ],
                ),
            ],
        )

        self.overlay.add_overlay(self.column)
        # the clock's size changes with its face and text: re-check where it
        # goes and how readable it is there
        self.column.connect("size-allocate", lambda *_: self._layout_soon())

        super().__init__(
            title="fabric-desktop",
            layer="bottom",
            anchor="top bottom left right",
            exclusivity="normal",
            # notes need typing; the desktop only takes the keyboard on click
            keyboard_mode="on-demand",
            monitor=monitor,
            child=self.overlay,
        )
        self.show_all()
        self.apply_settings()

    def do_destroy(self):
        self.fx.set_animating(False)
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.remove_provider_for_screen(screen, self._size_provider)
        WaylandWindow.do_destroy(self)

    # Settings and layout

    def enabled(self, widget: str) -> bool:
        """Whether `widget` shows on this monitor."""
        return self.manager.settings.enabled(widget, self.monitor_name)

    def apply_settings(self):
        settings = self.manager.settings
        self.face_stack.set_visible_child_name(settings.face)
        self.notes.set_visible(self.enabled("notes"))
        self._place_column()
        self.refresh()
        # the arc, visualizer or music card may have come or gone
        self._layout_soon()

    def _place_column(self):
        margin = self.sizes.margin
        if self.manager.settings.position == "auto":
            if self._auto_spot is not None:
                x, y = self._auto_spot
                self.column.set_halign(Gtk.Align.START)
                self.column.set_valign(Gtk.Align.START)
                self.column.set_margin_start(round(x))
                self.column.set_margin_top(round(y))
                self.column.set_margin_end(0)
                self.column.set_margin_bottom(0)
                return
            # until the wallpaper is measured, start from the classic place
        else:
            self._auto_spot = None
        position = self.manager.settings.position
        if position == "auto":
            position = "top"
        h_align, v_align = {
            "top": (Gtk.Align.CENTER, Gtk.Align.START),
            "center": (Gtk.Align.CENTER, Gtk.Align.CENTER),
            "bottom-left": (Gtk.Align.START, Gtk.Align.END),
            "bottom-right": (Gtk.Align.END, Gtk.Align.END),
        }[position]
        self.column.set_halign(h_align)
        self.column.set_valign(v_align)
        self.column.set_margin_top(margin if v_align == Gtk.Align.START else 0)
        # clear the visualizer along the bottom edge
        self.column.set_margin_bottom(margin * 2 if v_align == Gtk.Align.END else 0)
        self.column.set_margin_start(margin if h_align == Gtk.Align.START else 0)
        self.column.set_margin_end(margin if h_align == Gtk.Align.END else 0)

    # Minute updates

    def refresh(self):
        now = datetime.datetime.now()
        settings = self.manager.settings
        prayer_times = self.manager.prayer_times()

        on_the_hour = now.minute == 0 and self.enabled("moods")
        self.digital.update(now, settings.use_24h)
        self.faces["analog"].update(now, settings.use_24h)  # type: ignore[attr-defined]
        self.words.update(now, settings.use_24h, sweep=on_the_hour)
        self.date_label.set_label(now.strftime("%A, %B %-d"))
        self.update_focus()
        self.update_prayer()
        self.update_meta()
        self.update_memory()
        self.update_color(now, prayer_times)
        if prayer_times != self.fx.prayer_times:
            self.fx.prayer_times = prayer_times
            self._layout_soon()  # the arc moved: keep the clock clear of it
        self.update_fx()

    def update_prayer(self):
        service = _prayer_service()
        name, remaining = service.next_prayer, service.time_to_next_prayer
        if (
            not self.enabled("prayer")
            or name in (None, "None")
            or remaining in (None, "None")
        ):
            self.prayer_label.hide()
            return
        self.prayer_label.set_label(f"{name} in {str(remaining).removeprefix('0h ')}")
        self.prayer_label.show()

    def update_meta(self):
        parts = []
        if self.enabled("weather") and self.manager.weather.text:
            parts.append(self.manager.weather.text)
        if self.enabled("hijri") and (hijri := hijri_date()):
            parts.append(hijri)
        self.meta_label.set_label("  ·  ".join(parts))
        self.meta_label.set_visible(bool(parts))

    def update_memory(self):
        memory = self.manager.on_this_day.current
        if not self.enabled("on_this_day") or memory is None:
            self.memory.hide()
            return
        self.memory_label.set_label(memory.text)
        self.memory.set_tooltip_text(
            "Click to open the photo" if memory.path else memory.text
        )
        self.memory.show()

    def update_focus(self):
        focus = self.manager.focus
        if focus.running:
            self.digital.show_countdown(focus.remaining)
            ends = datetime.datetime.fromtimestamp(focus.ends_at_clock or 0)
            hour = ends.hour if self.manager.settings.use_24h else ends.hour % 12 or 12
            self.date_label.set_label(f"Focus  ·  until {hour}:{ends:%M}")
            self.column.add_style_class("focus")
        else:
            self.column.remove_style_class("focus")

    # Colour

    def set_accent(self, rgb: RGB | None):
        self._accent_source = rgb
        self._apply_tone(self.on_light if self.wall_map is not None else None)

    def _apply_tone(self, on_light: bool | None):
        if self._accent_source is None:
            self.accent, self.on_light = None, bool(on_light)
        else:
            self.accent, self.on_light = readable_accent(self._accent_source, on_light)
        self.update_color(datetime.datetime.now(), self.manager.prayer_times())

    # Wallpaper: placement and legibility

    def set_wallpaper(self, path: str | None):
        """Measure this monitor's wallpaper (when it changed)."""
        if path is None or path == self._map_path:
            return
        self._map_path = path
        width, height = self._monitor_size()

        def on_map(wall_map: WallpaperMap | None):
            if path != self._map_path:
                return  # the wallpaper changed again meanwhile
            self.wall_map = wall_map
            # a new wallpaper: let "auto" pick afresh
            self._auto_spot = None
            self._last_rect = None
            self._update_layout()

        build_map_async(path, width, height, on_map)

    def _monitor_size(self) -> tuple[int, int]:
        monitor = self.manager.display.get_monitor(self.monitor_index)
        if monitor is not None:
            geometry = monitor.get_geometry()
            return geometry.width, geometry.height
        return self.get_allocated_width() or 1920, self.get_allocated_height() or 1080

    def _layout_soon(self):
        if self._layout_id is None:
            self._layout_id = GLib.timeout_add(LAYOUT_DELAY_MS, self._update_layout)

    def _update_layout(self) -> bool:
        self._layout_id = None
        wall_map = self.wall_map
        width = self.column.get_allocated_width()
        height = self.column.get_allocated_height()
        if wall_map is None or width <= 1 or height <= 1:
            return False

        if self.manager.settings.position == "auto":
            spot = self._choose_spot(wall_map, width, height)
            if spot is not None and spot != self._auto_spot:
                self._auto_spot = spot
                self._place_column()
                return False  # the move reallocates the clock: check again then

        coords = self.column.translate_coordinates(self, 0, 0)
        if coords is None:
            return False
        rect = (coords[0], coords[1], width, height)
        if rect != self._last_rect:
            self._last_rect = rect
            self._apply_legibility(wall_map.stats(rect))
        return False

    def _choose_spot(
        self, wall_map: WallpaperMap, width: int, height: int
    ) -> tuple[float, float] | None:
        """The calmest readable spot for the clock, near the top centre."""
        monitor_w, monitor_h = wall_map.monitor_width, wall_map.monitor_height
        margin = self.sizes.margin
        # keep clear of the screen edges, and of the visualizer at the bottom
        bottom = margin * 2 if self.enabled("visualizer") else margin
        bounds = (margin, margin, monitor_w - 2 * margin, monitor_h - margin - bottom)
        home_x, home_y = monitor_w / 2, margin + height / 2

        def score(stats: RegionStats, x: float, y: float) -> float:
            _dark, contrast = text_contrast(stats)
            distance = math.hypot(
                (x + width / 2 - home_x) / monitor_w,
                (y + height / 2 - home_y) / monitor_h,
            )
            return (
                stats.busyness + 0.02 * max(0.0, 7 - contrast) + HOME_WEIGHT * distance
            )

        avoid = self._avoid()
        best = wall_map.calmest(width, height, bounds, avoid, score)
        if best is None:
            return None
        x, y, stats = best
        if self._auto_spot is not None:
            old_x, old_y = self._auto_spot
            fits = (
                bounds[0] <= old_x <= bounds[0] + bounds[2] - width
                and bounds[1] <= old_y <= bounds[1] + bounds[3] - height
                and wall_map.is_clear((old_x, old_y, width, height), avoid)
            )
            if fits:
                current = score(
                    wall_map.stats((old_x, old_y, width, height)), old_x, old_y
                )
                if score(stats, x, y) > current - MOVE_MARGIN:
                    return self._auto_spot
        return x, y

    def _avoid(self) -> list[tuple[float, float, float, float]]:
        """Areas the clock shouldn't cover: this monitor's music card and the
        prayer arc."""
        pad = self.sizes.margin / 2
        areas = [
            (
                w.x - pad,
                w.y - pad,
                w.player.card_w + 2 * pad,
                w.player.total_h + 2 * pad,
            )
            for w in self.manager.player_windows
            if w.monitor_name == self.monitor_name and w.get_visible()
        ]
        if self.enabled("prayer_arc"):
            areas += self.fx.arc_obstacles(*self._monitor_size())
        return areas

    def _apply_legibility(self, stats: RegionStats):
        """Pick light or dark text for what's behind the clock, and lay a
        soft scrim behind it where the wallpaper is too busy or mid-toned."""
        on_light, contrast = text_contrast(stats)
        need = (
            max(0.0, stats.busyness - BUSY_LIMIT) * 2.5
            + max(0.0, MIN_CONTRAST - contrast) * 0.06
        )
        rect = self._last_rect
        if rect is not None and (
            stats.busyness > BUSY_LIMIT or contrast < MIN_CONTRAST
        ):
            alpha = min(SCRIM_MAX_ALPHA, SCRIM_MIN_ALPHA + need)
            # light under dark text, dark under light text
            rgb = (0.98, 0.97, 0.95) if on_light else (0.04, 0.04, 0.07)
            self.fx.scrim = (rect, rgb, alpha)
        else:
            self.fx.scrim = None
        self._apply_tone(on_light)

    def update_color(self, now: datetime.datetime, prayer_times: dict[str, str]):
        color = self.accent or (240, 240, 245)
        if self.enabled("moods") and (mood := mood_color(now, prayer_times)):
            color = _blend(color, mood, 0.55 if not self.on_light else 0.35)
        self.column.set_style(f"color: rgb({color[0]}, {color[1]}, {color[2]});")
        if self.on_light:
            self.column.add_style_class("on-light")
        else:
            self.column.remove_style_class("on-light")
        self.faces["analog"].queue_draw()
        self.fx.ink = (color[0] / 255, color[1] / 255, color[2] / 255)
        self.fx.queue_draw()

    # Drawn layer

    def update_fx(self):
        visible = self.manager.visibility.visible(self.monitor_name)
        self.fx.show_arc = self.enabled("prayer_arc")
        self.fx.show_bars = self.enabled("visualizer") and self.manager.cava.running
        self.fx.set_animating(visible and self.fx.show_bars)
        self.fx.queue_draw()

    # Greeting

    def show_greeting(self):
        if not self.enabled("greeting") or self.manager.focus.running:
            return
        self.greeting_label.set_label(greeting())
        self.date_stack.set_visible_child_name("greeting")
        if self._greeting_id is not None:
            GLib.source_remove(self._greeting_id)

        def back():
            self._greeting_id = None
            self.date_stack.set_visible_child_name("date")
            return False

        self._greeting_id = GLib.timeout_add(GREETING_MS, back)

    # Input

    def _on_face_scroll(self, _widget, event: Gdk.EventScroll):
        if step := _scroll_step(event):
            self.manager.cycle_face(step)
        return True

    def _on_memory_press(self, _widget, event: Gdk.EventButton):
        memory = self.manager.on_this_day.current
        if event.button == 1 and memory and memory.path:
            run_command_async(["xdg-open", memory.path])
            return True
        return False

    def _on_background_press(self, _widget, event: Gdk.EventButton):
        if event.button == 3:
            self.show_menu(event)
            return True
        return False

    # Menu

    def show_menu(self, event: Gdk.EventButton):
        manager = self.manager
        settings = manager.settings
        menu = Gtk.Menu()
        menu.get_style_context().add_class("tray")  # shared menu styling

        def item(label: str, callback: Callable[[], None], parent: Gtk.Menu = menu):
            entry = Gtk.MenuItem(label=label)
            entry.connect("activate", lambda *_: callback())
            parent.append(entry)

        def check(
            label: str,
            active: bool,
            callback: Callable[[], None],
            parent: Gtk.Menu,
            radio: bool = False,
        ):
            entry = Gtk.CheckMenuItem(label=label)
            entry.set_draw_as_radio(radio)
            entry.set_active(active)
            entry.connect("toggled", lambda *_: callback())
            parent.append(entry)

        def submenu(label: str) -> Gtk.Menu:
            sub = Gtk.Menu()
            sub.get_style_context().add_class("tray")
            entry = Gtk.MenuItem(label=label)
            entry.set_submenu(sub)
            menu.append(entry)
            return sub

        if self.enabled("notes"):
            # where the click landed, in this window's coordinates
            coords = _widget_coords(event, self)
            item("New note", lambda: self.notes.add_note(*coords))
        if manager.focus.running:
            item("Stop focus timer", manager.focus.cancel)
        else:
            item("Focus for 25 minutes", lambda: manager.focus.start(25))
            item("Focus for 50 minutes", lambda: manager.focus.start(50))
        menu.append(Gtk.SeparatorMenuItem())

        clock = submenu("Clock")
        check("24-hour time", settings.use_24h, manager.toggle_24h, clock)
        clock.append(Gtk.SeparatorMenuItem())
        for face in FACES:
            check(
                face.capitalize(),
                settings.face == face,
                lambda f=face: manager.set_face(f),
                clock,
                radio=True,
            )
        clock.append(Gtk.SeparatorMenuItem())
        for position in POSITIONS:
            check(
                "Auto (calmest spot)"
                if position == "auto"
                else position.replace("-", " ").capitalize(),
                settings.position == position,
                lambda p=position: manager.set_position(p),
                clock,
                radio=True,
            )

        player_size = submenu("Music player size")
        current_size = settings.player_size(self.monitor_name)
        for size in PLAYER_SIZES:
            check(
                size.capitalize(),
                current_size == size,
                lambda z=size: manager.set_player_size(self.monitor_name, z),
                player_size,
                radio=True,
            )

        # widgets are chosen per display; the menu edits this one
        widgets = submenu(f"Widgets on {self.monitor_name}")
        for name, (label, _default) in WIDGETS.items():
            if name == "visualizer" and not manager.cava.available:
                label += " (needs cava)"
            check(
                label,
                self.enabled(name),
                lambda n=name: manager.toggle_widget(n, self.monitor_name),
                widgets,
            )
        if len(manager.windows) > 1:
            widgets.append(Gtk.SeparatorMenuItem())
            item(
                "Use these on all displays",
                lambda: manager.widgets_everywhere(self.monitor_name),
                widgets,
            )

        menu.show_all()
        # Wayland places popups relative to a parent
        menu.attach_to_widget(self.background, None)
        # keep a reference, or the menu is garbage collected while open
        self._menu = menu
        menu.popup_at_pointer(event)


def _widget_coords(event: Gdk.EventButton, window: Gtk.Window) -> tuple[int, int]:
    """The event position relative to `window`."""
    origin = window.get_window()
    if origin is None:
        return round(event.x), round(event.y)
    _ok, wx, wy = origin.get_origin()
    return max(0, round(event.x_root - wx)), max(0, round(event.y_root - wy))


class DesktopManager:
    """One desktop per monitor, kept in step with settings, time and services."""

    def __init__(self):
        self.settings = DesktopSettings()
        self.visibility = DesktopVisibility()
        self.focus = FocusTimer()
        self.cava = config.cava
        self.weather = WeatherService()
        self.on_this_day = OnThisDay()
        self.notes = NotesStore()
        self.media = get_media_state()
        self.windows: list[DesktopWindow] = []
        self.player_windows: list[MusicPlayerWindow] = []
        self._hidden_since: dict[str, float] = {}

        display = Gdk.Display.get_default()
        if display is None:
            raise RuntimeError("no default Gdk display")
        self.display = display
        self._build()
        display.connect("monitor-added", lambda *_: self._rebuild_soon())
        display.connect("monitor-removed", lambda *_: self._rebuild_soon())

        _MinuteTicker(self.refresh)
        prayer = _prayer_service()
        prayer.connect(
            "notify::time-to-next-prayer",
            lambda *_: self._each(DesktopWindow.update_prayer),
        )
        prayer.connect("update", lambda *_: self.refresh())

        config.wallpaper_accent.connect("changed", lambda *_: self.update_accents())
        config.wallpaper_accent.connect(
            "changed", lambda *_: self.update_player_palette()
        )
        self.update_accents()

        self.focus.connect("changed", lambda *_: self._on_focus_changed())
        self.weather.connect(
            "changed", lambda *_: self._each(DesktopWindow.update_meta)
        )
        self.on_this_day.connect(
            "changed", lambda *_: self._each(DesktopWindow.update_memory)
        )
        self.cava.connect("frame", lambda *_: None)
        self.visibility.connect("changed", lambda *_: self._on_visibility_changed())

        self.media.connect("changed", lambda *_: self._on_players_changed())
        self.media.connect(
            "lyrics-changed",
            lambda *_: [w.player.lyrics_changed() for w in self.player_windows],
        )
        config.theme.connect(
            "notify::is-light", lambda *_: self.update_player_palette()
        )
        self._on_players_changed()

        # say hello once the desktop is up
        GLib.timeout_add(1500, lambda: self._each(DesktopWindow.show_greeting) or False)

    # Windows

    def _monitor_names(self) -> list[str]:
        screen = self.display.get_default_screen()
        with warnings.catch_warnings():
            # deprecated, but GTK3 has nothing else that gives connector names
            warnings.simplefilter("ignore", DeprecationWarning)
            return [
                screen.get_monitor_plug_name(i) or str(i)
                for i in range(self.display.get_n_monitors())
            ]

    def _build(self):
        self.windows = []
        self.player_windows = []
        for i, name in enumerate(self._monitor_names()):
            monitor = self.display.get_monitor(i)
            height = monitor.get_geometry().height if monitor else 1080
            self.windows.append(DesktopWindow(self, i, name, height))
            if monitor is not None:
                self.player_windows.append(
                    MusicPlayerWindow(
                        i,
                        name,
                        monitor.get_geometry(),
                        self.media,
                        self.cava,
                        self.settings.player_positions.get(name),
                        on_moved=self._save_player_position,
                        on_toggle_lyrics=lambda w: self.toggle_widget(
                            "lyrics", w.monitor_name
                        ),
                    )
                )
        self.apply_player_settings()

    def _rebuild_soon(self):
        # monitor numbering shifts on hotplug; rebuild once things settle
        def rebuild():
            for window in [*self.windows, *self.player_windows]:
                window.destroy()
            self._build()
            self.update_accents()
            return False

        GLib.timeout_add(500, rebuild)

    def _each(self, method: Callable[[DesktopWindow], object]):
        for window in self.windows:
            method(window)

    def refresh(self):
        self.on_this_day.refresh()
        self._each(DesktopWindow.refresh)

    def prayer_times(self) -> dict[str, str]:
        return dict(_prayer_service().prayer_info)

    def update_accents(self):
        for window in self.windows:
            window.set_accent(config.wallpaper_accent.color_for(window.monitor_name))
            window.set_wallpaper(config.wallpaper_accent.path_for(window.monitor_name))

    # Settings

    def _changed(self):
        self.settings.save()
        self._update_cava()
        self._each(DesktopWindow.apply_settings)
        self.apply_player_settings()

    # Music player

    def apply_player_settings(self):
        for window in self.player_windows:
            name = window.monitor_name
            window.player.set_show_lyrics(self.settings.enabled("lyrics", name))
            window.player.set_scale(PLAYER_SIZES[self.settings.player_size(name)])
            window.set_visible(self.settings.enabled("music_player", name))
        self.update_player_palette()

    def update_player_palette(self):
        from fabric_config.services.wallpaper_accent import theme_accent_rgb

        is_light = config.theme.is_light
        rgb = config.wallpaper_accent.accent_rgb()
        accent = theme_accent_rgb(rgb, is_light) if rgb else None
        for window in self.player_windows:
            window.player.set_palette(is_light, accent)

    def _save_player_position(self, window: MusicPlayerWindow):
        self.settings.player_positions[window.monitor_name] = [window.x, window.y]
        self.settings.save()

    def toggle_24h(self):
        self.settings.use_24h = not self.settings.use_24h
        self._changed()

    def set_face(self, face: str):
        self.settings.face = face
        self._changed()

    def cycle_face(self, step: int):
        index = (FACES.index(self.settings.face) + step) % len(FACES)
        self.set_face(FACES[index])

    def set_position(self, position):
        self.settings.position = position
        self._changed()

    def set_player_size(self, monitor: str, size: str):
        self.settings.player_sizes[monitor] = size
        self._changed()

    def toggle_widget(self, name: str, monitor: str):
        self.settings.set_widget(
            name, monitor, not self.settings.enabled(name, monitor)
        )
        self._changed()

    def widgets_everywhere(self, monitor: str):
        self.settings.use_everywhere(monitor)
        self._changed()

    # Focus

    def _on_focus_changed(self):
        for window in self.windows:
            if self.focus.running:
                window.update_focus()
            else:
                window.refresh()

    # Visibility

    def _on_visibility_changed(self):
        now = GLib.get_monotonic_time() / 1_000_000
        for window in self.windows:
            name = window.monitor_name
            if self.visibility.visible(name):
                hidden_since = self._hidden_since.pop(name, None)
                if (
                    hidden_since is not None
                    and now - hidden_since > GREET_AFTER_HIDDEN_S
                ):
                    window.show_greeting()
            else:
                self._hidden_since.setdefault(name, now)
        self._update_cava()
        self._each(DesktopWindow.update_fx)
        for window in self.player_windows:
            window.player.set_desktop_visible(
                self.visibility.visible(window.monitor_name)
            )

    # Media

    def _on_players_changed(self):
        self._update_cava()
        for window in self.player_windows:
            window.player.update_track()
        self._each(DesktopWindow.update_fx)

    def current_player(self):
        return self.media.current_player()

    def _update_cava(self):
        player = self.current_player()
        # wanted while something plays and a visible desktop shows levels:
        # the visualizer, or the music card's seek bar
        wanted = (
            player is not None
            and player.playback_status == "Playing"
            and any(
                (
                    self.settings.enabled("visualizer", w.monitor_name)
                    or self.settings.enabled("music_player", w.monitor_name)
                )
                and self.visibility.visible(w.monitor_name)
                for w in self.windows
            )
        )
        self.cava.set_wanted("desktop", wanted)


class _MinuteTicker:
    """Calls back on each minute boundary rather than polling every second."""

    def __init__(self, callback: Callable[[], None]):
        self._callback = callback
        self._schedule()

    def _schedule(self):
        now = datetime.datetime.now()
        ms = (60 - now.second) * 1000 - now.microsecond // 1000
        # land just after the boundary, not just before it
        GLib.timeout_add(ms + 50, self._tick)

    def _tick(self):
        self._callback()
        self._schedule()
        return False
