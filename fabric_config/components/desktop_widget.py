import colorsys
import datetime
import json
import math
import os
import warnings
from collections.abc import Callable
from typing import Literal

from fabric.utils import monitor_file
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.stack import Stack
from fabric.widgets.wayland import WaylandWindow
from gi.repository import Gdk, GLib, Gtk
from loguru import logger

from fabric_config.utils.accent import grab_dominant_color_threaded
from fabric_config.utils.wallpaper import (
    LAST_WALLPAPER_FILE,
    query_active_wallpapers,
    wallpaper_for_monitor,
)

# Layout. POSITION picks where the clock sits on each monitor; SIZE scales it
# (matching .clock-size-* rules in _desktop-widget.scss).
Position = Literal["top-center", "center", "top-left", "bottom-left", "bottom-right"]
POSITION: Position = "top-center"
SIZE: Literal["small", "medium", "large"] = "large"
EDGE_MARGIN = 60

FACES = ("digital", "analog", "words")
ANALOG_SIZE = 260
PROGRESS_WIDTH = 180  # px, the day-progress line under the time

SETTINGS_FILE = os.path.join(GLib.get_user_cache_dir(), "fabric", "desktop_clock.json")

_POSITIONS: dict[str, tuple[str, str]] = {
    # anchor, margin (top right bottom left)
    "top-center": ("top", f"{EDGE_MARGIN}px 0 0 0"),
    "center": ("", "0"),
    "top-left": ("top left", f"{EDGE_MARGIN}px 0 0 {EDGE_MARGIN}px"),
    "bottom-left": ("bottom left", f"0 0 {EDGE_MARGIN}px {EDGE_MARGIN}px"),
    "bottom-right": ("bottom right", f"0 {EDGE_MARGIN}px {EDGE_MARGIN}px 0"),
}


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
    r, g, b = colorsys.hls_to_rgb(h, 0.2 if on_light else 0.82, min(s, 0.5))
    return f"rgb({round(r * 255)}, {round(g * 255)}, {round(b * 255)})", on_light


# Faces


class DigitalFace(EventBox):
    def __init__(self, on_toggle_24h: Callable[[], None]):
        self.time_label = Label(name="clock-time")
        self.ampm_label = Label(name="clock-ampm", v_align="start")
        super().__init__(
            events=["button-press"],
            child=Box(
                h_align="center",
                spacing=8,
                children=[self.time_label, self.ampm_label],
            ),
            tooltip_text="Click to switch 12/24-hour time",
        )
        self.connect(
            "button-press-event",
            lambda _w, e: on_toggle_24h() if e.button == 1 else None,
        )

    def update(self, now: datetime.datetime, use_24h: bool):
        if use_24h:
            self.time_label.set_label(now.strftime("%H:%M"))
            self.ampm_label.hide()
        else:
            self.time_label.set_label(f"{now.hour % 12 or 12}:{now:%M}")
            self.ampm_label.set_label(now.strftime("%p"))
            self.ampm_label.show()


class AnalogFace(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.set_size_request(ANALOG_SIZE, ANALOG_SIZE)
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

        # an outline in the contrasting colour keeps every stroke readable
        # over busy wallpapers without a filled backdrop
        o = 1.0 if self.on_light else 0.0
        outline = (o, o, o, 0.6 if self.on_light else 0.5)
        ink = (color.red, color.green, color.blue)

        def stroke(width: float, alpha: float = 1.0):
            cr.set_source_rgba(*outline)
            cr.set_line_width(width + 2.5)
            cr.stroke_preserve()
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

        cr.arc(cx, cy, 8, 0, 2 * math.pi)
        cr.set_source_rgba(*outline)
        cr.fill_preserve()
        cr.arc(cx, cy, 6.5, 0, 2 * math.pi)
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
    def __init__(self, manager: "DesktopClocks", monitor: int, monitor_name: str):
        self.manager = manager
        self.monitor_name = monitor_name
        self.faces = {
            "digital": DigitalFace(manager.toggle_24h),
            "analog": AnalogFace(),
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

        self.progress_fill = Box(name="clock-progress-fill", h_align="start")
        self.progress = Box(
            name="clock-progress",
            h_align="center",
            size=(PROGRESS_WIDTH, -1),
            children=self.progress_fill,
            tooltip_text="How much of the day has passed",
        )

        self.date_button = Button(
            name="clock-date",
            h_align="center",
            on_clicked=lambda *_: self._toggle_calendar(),
        )
        self.prayer_label = Label(name="clock-prayer", visible=False)

        self.calendar = Gtk.Calendar(name="clock-calendar")
        self.calendar_revealer = Revealer(
            transition_type="slide-down",
            transition_duration=200,
            child=Box(h_align="center", children=self.calendar),
        )

        self.root = Box(
            name="desktop-clock",
            style_classes=[f"clock-size-{SIZE}"],
            orientation="v",
            spacing=10,
            h_align="center",
            children=[
                self.face_events,
                self.progress,
                self.date_button,
                self.prayer_label,
                self.calendar_revealer,
            ],
        )

        anchor, margin = _POSITIONS[POSITION]
        super().__init__(
            layer="bottom",
            anchor=anchor,
            margin=margin,
            monitor=monitor,
            exclusivity="none",
            keyboard_mode="none",
            child=self.root,
        )
        self.show_all()
        self.face_stack.set_visible_child_name(manager.settings.face)
        self.refresh()

    def refresh(self):
        now = datetime.datetime.now()
        use_24h = self.manager.settings.use_24h
        for face in self.faces.values():
            face.update(now, use_24h)
        self.date_button.set_label(now.strftime("%A, %B %-d"))
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        fraction = (now - midnight).total_seconds() / 86400
        self.progress_fill.set_size_request(
            max(1, round(PROGRESS_WIDTH * fraction)), -1
        )
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

    def _toggle_calendar(self):
        revealing = not self.calendar_revealer.get_reveal_child()
        if revealing:
            # open on today, not wherever it was left
            today = datetime.date.today()
            self.calendar.select_month(today.month - 1, today.year)
            self.calendar.select_day(today.day)
        self.calendar_revealer.set_reveal_child(revealing)


class DesktopClocks:
    """One clock per monitor, kept in step with settings, time and wallpaper."""

    def __init__(self):
        self.settings = ClockSettings()
        self.windows: list[ClockWidget] = []
        self._accent_cache: dict[str, Accent | None] = {}
        # windows waiting on an extraction already running for that path
        self._accent_waiting: dict[str, list[ClockWidget]] = {}
        self._accent_timer: int | None = None

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

        # the wallpaper picker saves its choice here; startup scripts may set
        # one directly, so ask hyprpaper too
        self._wallpaper_monitor = monitor_file(LAST_WALLPAPER_FILE)
        self._wallpaper_monitor.connect(
            "changed", lambda *_: self._update_accents_soon()
        )
        GLib.timeout_add(1500, lambda: self.update_accents() or False)

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
        self.windows = [
            ClockWidget(self, i, name) for i, name in enumerate(self._monitor_names())
        ]

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

    def _update_accents_soon(self):
        # one save fires several file events, and hyprpaper switches a moment
        # after the picker saves: wait for the burst to settle, then update once
        if self._accent_timer is not None:
            GLib.source_remove(self._accent_timer)

        def fire():
            self._accent_timer = None
            self.update_accents()
            return False

        self._accent_timer = GLib.timeout_add(500, fire)

    def update_accents(self):
        def on_active(active: dict[str, str]):
            for window in self.windows:
                path = active.get(window.monitor_name) or wallpaper_for_monitor(
                    window.monitor_name
                )
                if path:
                    self._apply_accent(window, path)

        query_active_wallpapers(on_active)

    def _apply_accent(self, window: ClockWidget, path: str):
        if path in self._accent_cache:
            window.set_accent(self._accent_cache[path])
            return

        waiting = self._accent_waiting.get(path)
        if waiting is not None:
            # same wallpaper on another monitor: share the running extraction
            waiting.append(window)
            return
        self._accent_waiting[path] = [window]

        def on_color(rgb):
            accent = readable_accent(rgb) if rgb else None
            self._accent_cache[path] = accent
            for waiting_window in self._accent_waiting.pop(path, []):
                if waiting_window in self.windows:
                    waiting_window.set_accent(accent)
            return False

        grab_dominant_color_threaded(path, on_color)
