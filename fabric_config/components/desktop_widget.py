import colorsys
import datetime
import json
import math
import os
import warnings
from dataclasses import dataclass
from collections.abc import Callable
from typing import Literal

from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.wayland import WaylandWindow
from gi.repository import Gdk, GLib, Gtk
from loguru import logger

import fabric_config.config as config

# Layout. POSITION picks where the clock sits on each monitor. Everything is
# sized from the monitor's height, so screens of different resolutions get a
# clock taking up the same share of the screen; SCALE grows or shrinks it.
Position = Literal["top-center", "center", "top-left", "bottom-left", "bottom-right"]
POSITION: Position = "top-center"
SCALE = 1.0

FACES = ("digital", "analog", "words")

SETTINGS_FILE = os.path.join(GLib.get_user_cache_dir(), "fabric", "desktop_clock.json")

_POSITIONS: dict[str, tuple[str, str]] = {
    # anchor, margin (top right bottom left) with {m} the edge margin
    "top-center": ("top", "{m}px 0 0 0"),
    "center": ("", "0"),
    "top-left": ("top left", "{m}px 0 0 {m}px"),
    "bottom-left": ("bottom left", "0 0 {m}px {m}px"),
    "bottom-right": ("bottom right", "0 {m}px {m}px 0"),
}


@dataclass(frozen=True)
class ClockSizes:
    """Pixel sizes for one monitor, all derived from its height."""

    time: int
    date: int
    prayer: int
    words: int
    analog: int
    margin: int

    @classmethod
    def for_height(cls, height: int) -> "ClockSizes":
        time = round(height * 0.2 * SCALE)
        return cls(
            time=time,
            date=round(time * 0.17),
            prayer=round(time * 0.11),
            words=round(height * 0.04 * SCALE),
            analog=round(height * 0.32 * SCALE),
            margin=round(height * 0.06),
        )


def _sizes_css(cls: str, sizes: ClockSizes) -> str:
    """Per-monitor size rules, scoped by the window's class."""
    root = f"#desktop-clock.{cls}"
    # Inter Display's line box is taller than its digits; pull the date and
    # prayer line in close, like the macOS lock screen
    return f"""
{root} #clock-time {{
  font-size: {sizes.time}px;
  letter-spacing: -{round(sizes.time * 0.025)}px;
  margin-top: -{round(sizes.time * 0.12)}px;
  margin-bottom: -{round(sizes.time * 0.14)}px;
}}
{root} #clock-date {{ font-size: {sizes.date}px; }}
{root} #clock-prayer {{ font-size: {sizes.prayer}px; }}
{root} #clock-words .clock-word {{ font-size: {sizes.words}px; }}
"""


class ClockSettings:
    """12/24-hour and face choice, shared by every monitor's clock."""

    def __init__(self):
        self.use_24h = False
        self.face = FACES[0]
        try:
            with open(SETTINGS_FILE) as f:
                data = json.load(f)
            self.use_24h = bool(data.get("24h", False))
            if data.get("face") in FACES:
                self.face = data["face"]
        except (OSError, ValueError, AttributeError):
            pass

    def save(self):
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, "w") as f:
                json.dump({"24h": self.use_24h, "face": self.face}, f)
        except OSError as e:
            logger.warning(f"[Desktop Clock] Couldn't save settings: {e}")


class MinuteTicker:
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


# (css colour, wallpaper is light)
Accent = tuple[str, bool]


def readable_accent(rgb: tuple[int, int, int]) -> Accent:
    """
    A tint of a wallpaper's dominant colour that reads against it: light on
    dark wallpapers, dark on light ones.
    """
    red, green, blue = (c / 255 for c in rgb)
    on_light = 0.2126 * red + 0.7152 * green + 0.0722 * blue > 0.55
    h, _light, s = colorsys.rgb_to_hls(red, green, blue)
    # mostly white (or near-black) with just a hint of the wallpaper, like
    # macOS's vibrant lock-screen clock
    r, g, b = colorsys.hls_to_rgb(h, 0.2 if on_light else 0.93, min(s, 0.4))
    return f"rgb({round(r * 255)}, {round(g * 255)}, {round(b * 255)})", on_light


# Faces


class DigitalFace(EventBox):
    def __init__(self, on_toggle_24h: Callable[[], None]):
        self.time_label = Label(name="clock-time")
        super().__init__(
            events=["button-press"],
            child=self.time_label,
            h_align="center",
            tooltip_text="Click to switch 12/24-hour time",
        )
        self.connect(
            "button-press-event",
            lambda _w, e: on_toggle_24h() if e.button == 1 else None,
        )

    def update(self, now: datetime.datetime, use_24h: bool):
        # like the macOS lock screen: no leading zero, no AM/PM
        hour = now.hour if use_24h else now.hour % 12 or 12
        self.time_label.set_label(f"{hour}:{now:%M}")


class AnalogFace(Gtk.DrawingArea):
    def __init__(self, size: int):
        super().__init__()
        self.set_size_request(size, size)
        self.set_halign(Gtk.Align.CENTER)
        self.get_style_context().add_class("clock-analog")
        self._now = datetime.datetime.now()
        # dial fill and hand shadows contrast with the wallpaper
        self.on_light = False
        self.connect("draw", self._on_draw)

    def update(self, now: datetime.datetime, _use_24h: bool):
        self._now = now
        self.queue_draw()

    def _on_draw(self, widget: Gtk.Widget, cr):
        color = widget.get_style_context().get_color(Gtk.StateFlags.NORMAL)
        w, h = widget.get_allocated_width(), widget.get_allocated_height()
        cx, cy, radius = w / 2, h / 2, min(w, h) / 2 - 6
        cr.set_line_cap(1)  # round

        # a faint offset shadow lifts the strokes off the wallpaper
        o = 1.0 if self.on_light else 0.0
        shadow = (o, o, o, 0.2)
        ink = (color.red, color.green, color.blue)

        def stroke(width: float, alpha: float = 1.0):
            path = cr.copy_path()
            cr.save()
            cr.translate(0, max(1.5, width * 0.3))
            cr.new_path()
            cr.append_path(path)
            cr.set_source_rgba(*shadow)
            cr.set_line_width(width + 1)
            cr.stroke()
            cr.restore()
            cr.new_path()
            cr.append_path(path)
            cr.set_source_rgba(*ink, alpha)
            cr.set_line_width(width)
            cr.stroke()

        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        stroke(1.5, 0.5)

        for i in range(12):
            angle = i * math.pi / 6
            major = i % 3 == 0
            inner = radius * (0.80 if major else 0.86)
            cr.move_to(cx + inner * math.sin(angle), cy - inner * math.cos(angle))
            cr.line_to(
                cx + radius * 0.92 * math.sin(angle),
                cy - radius * 0.92 * math.cos(angle),
            )
            stroke(5 if major else 2.5, 1 if major else 0.7)

        minute = self._now.minute
        hour = self._now.hour % 12 + minute / 60
        hands = (
            (hour * math.pi / 6, radius * 0.5, 9),
            (minute * math.pi / 30, radius * 0.76, 5),
        )
        for angle, length, width in hands:
            cr.move_to(cx, cy)
            cr.line_to(cx + length * math.sin(angle), cy - length * math.cos(angle))
            stroke(width)

        cr.arc(cx, cy, 7, 0, 2 * math.pi)
        cr.set_source_rgba(*ink, 1)
        cr.fill()
        return False


# (id, text) per row; ids distinguish the minute "FIVE"/"TEN" from the hours
_WORD_ROWS = [
    [("it", "IT"), ("is", "IS"), ("half", "HALF"), ("m10", "TEN")],
    [("quarter", "QUARTER"), ("twenty", "TWENTY")],
    [("m5", "FIVE"), ("minutes", "MINUTES"), ("to", "TO")],
    [("past", "PAST"), ("h1", "ONE"), ("h3", "THREE")],
    [("h2", "TWO"), ("h4", "FOUR"), ("h5", "FIVE")],
    [("h6", "SIX"), ("h7", "SEVEN"), ("h8", "EIGHT")],
    [("h9", "NINE"), ("h10", "TEN"), ("h11", "ELEVEN")],
    [("h12", "TWELVE"), ("oclock", "O'CLOCK")],
]
_MINUTE_WORDS = {
    0: ["oclock"],
    5: ["m5", "minutes", "past"],
    10: ["m10", "minutes", "past"],
    15: ["quarter", "past"],
    20: ["twenty", "minutes", "past"],
    25: ["twenty", "m5", "minutes", "past"],
    30: ["half", "past"],
    35: ["twenty", "m5", "minutes", "to"],
    40: ["twenty", "minutes", "to"],
    45: ["quarter", "to"],
    50: ["m10", "minutes", "to"],
    55: ["m5", "minutes", "to"],
}


def lit_words(now: datetime.datetime) -> set[str]:
    rounded = now.minute // 5 * 5
    hour = now.hour + (1 if rounded > 30 else 0)
    return {"it", "is", f"h{hour % 12 or 12}", *_MINUTE_WORDS[rounded]}


class WordFace(Box):
    def __init__(self):
        super().__init__(orientation="v", h_align="center", name="clock-words")
        self.words: dict[str, Label] = {}
        for row in _WORD_ROWS:
            line = Box(h_align="center", spacing=14)
            for word_id, text in row:
                label = Label(text, style_classes=["clock-word"])
                self.words[word_id] = label
                line.add(label)
            self.add(line)

    def update(self, now: datetime.datetime, _use_24h: bool):
        lit = lit_words(now)
        for word_id, label in self.words.items():
            if word_id in lit:
                label.add_style_class("lit")
            else:
                label.remove_style_class("lit")


# Window


def _prayer_service():
    from fabric_config.components.bar.widgets.prayer_times import (
        _get_prayer_service,
    )

    return _get_prayer_service()


class ClockWidget(WaylandWindow):
    def __init__(
        self,
        manager: "DesktopClocks",
        monitor: int,
        monitor_name: str,
        monitor_height: int,
    ):
        self.manager = manager
        self.monitor_name = monitor_name
        self.sizes = ClockSizes.for_height(monitor_height)
        # a screen-wide provider whose rules only match this window's clock
        size_class = "clock-" + "".join(c if c.isalnum() else "-" for c in monitor_name)
        self._size_provider = Gtk.CssProvider()
        self._size_provider.load_from_data(_sizes_css(size_class, self.sizes).encode())
        screen = Gdk.Screen.get_default()
        if screen is not None:
            # above the app stylesheet: between providers GTK goes by
            # priority, not selector specificity
            Gtk.StyleContext.add_provider_for_screen(
                screen, self._size_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 10
            )
        self.faces = {
            "digital": DigitalFace(manager.toggle_24h),
            "analog": AnalogFace(self.sizes.analog),
            "words": WordFace(),
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
        self.face_events = EventBox(
            events=["scroll", "smooth-scroll"],
            child=self.face_stack,
            on_scroll_event=self._on_scroll,
        )

        self.date_label = Label(name="clock-date", h_align="center")
        self.prayer_label = Label(name="clock-prayer", visible=False)

        self.root = Box(
            name="desktop-clock",
            style_classes=[size_class],
            orientation="v",
            h_align="center",
            children=[
                self.date_label,
                self.face_events,
                self.prayer_label,
            ],
        )

        anchor, margin = _POSITIONS[POSITION]
        super().__init__(
            layer="bottom",
            anchor=anchor,
            margin=margin.format(m=self.sizes.margin),
            monitor=monitor,
            exclusivity="none",
            keyboard_mode="none",
            child=self.root,
        )
        self.show_all()
        self.face_stack.set_visible_child_name(manager.settings.face)
        self.refresh()

    def do_destroy(self):
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.remove_provider_for_screen(screen, self._size_provider)
        WaylandWindow.do_destroy(self)

    def refresh(self):
        now = datetime.datetime.now()
        use_24h = self.manager.settings.use_24h
        for face in self.faces.values():
            face.update(now, use_24h)
        self.date_label.set_label(now.strftime("%A, %B %-d"))
        self.update_prayer()

    def update_prayer(self):
        service = _prayer_service()
        name, remaining = service.next_prayer, service.time_to_next_prayer
        if name in (None, "None") or remaining in (None, "None"):
            self.prayer_label.hide()
            return
        remaining = str(remaining).removeprefix("0h ")
        self.prayer_label.set_label(f"{name} in {remaining}")
        self.prayer_label.show()

    def show_face(self, face: str):
        self.face_stack.set_visible_child_name(face)

    def set_accent(self, accent: Accent | None):
        color, on_light = accent if accent else (None, False)
        self.root.set_style(f"color: {color};" if color else "")
        if on_light:
            self.root.add_style_class("on-light")
        else:
            self.root.remove_style_class("on-light")
        analog = self.faces["analog"]
        assert isinstance(analog, AnalogFace)
        analog.on_light = on_light
        analog.queue_draw()

    def _on_scroll(self, _widget, event: Gdk.EventScroll):
        match event.direction:
            case Gdk.ScrollDirection.UP:
                step = -1
            case Gdk.ScrollDirection.DOWN:
                step = 1
            case Gdk.ScrollDirection.SMOOTH:
                step = 1 if event.delta_y > 0 else -1 if event.delta_y < 0 else 0
            case _:
                step = 0
        if step:
            self.manager.cycle_face(step)
        return True


class DesktopClocks:
    """One clock per monitor, kept in step with settings, time and wallpaper."""

    def __init__(self):
        self.settings = ClockSettings()
        self.windows: list[ClockWidget] = []

        display = Gdk.Display.get_default()
        if display is None:
            raise RuntimeError("no default Gdk display")
        self.display = display
        self._build()
        display.connect("monitor-added", lambda *_: self._rebuild_soon())
        display.connect("monitor-removed", lambda *_: self._rebuild_soon())

        self._ticker = MinuteTicker(self.refresh)
        prayer = _prayer_service()
        prayer.connect(
            "notify::time-to-next-prayer",
            lambda *_: [w.update_prayer() for w in self.windows],
        )

        # tint each clock from its own monitor's wallpaper
        config.wallpaper_accent.connect("changed", lambda *_: self.update_accents())
        self.update_accents()

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
        for i, name in enumerate(self._monitor_names()):
            monitor = self.display.get_monitor(i)
            height = monitor.get_geometry().height if monitor else 1080
            self.windows.append(ClockWidget(self, i, name, height))

    def _rebuild_soon(self):
        # monitor numbering shifts on hotplug; rebuild once things settle
        def rebuild():
            for window in self.windows:
                window.destroy()
            self._build()
            self.update_accents()
            return False

        GLib.timeout_add(500, rebuild)

    def refresh(self):
        for window in self.windows:
            window.refresh()

    def toggle_24h(self):
        self.settings.use_24h = not self.settings.use_24h
        self.settings.save()
        self.refresh()

    def cycle_face(self, step: int):
        index = (FACES.index(self.settings.face) + step) % len(FACES)
        self.settings.face = FACES[index]
        self.settings.save()
        for window in self.windows:
            window.show_face(self.settings.face)

    # Wallpaper accent

    def update_accents(self):
        for window in self.windows:
            rgb = config.wallpaper_accent.color_for(window.monitor_name)
            window.set_accent(readable_accent(rgb) if rgb else None)
