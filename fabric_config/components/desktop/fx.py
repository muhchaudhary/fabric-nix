"""
The desktop's drawn layer, under the clock: seasonal particles, the prayer
arc across the lower half and the audio visualizer along the bottom.

It animates only while something is moving and the monitor's desktop is
showing; otherwise it redraws once a minute for the arc.
"""

import datetime
import math
import os
import random
from dataclasses import dataclass

import cairo
from fabric.core.service import Service, Signal
from gi.repository import Gio, GLib, Gtk
from loguru import logger

FRAME_MS = 33  # ~30 fps
CAVA_BARS = 64
CAVA_CONFIG = os.path.join(GLib.get_user_cache_dir(), "fabric", "cava.conf")


# Audio (cava)


class Cava(Service):
    """
    Runs cava while someone wants bars, reading its raw ASCII output: one
    line per frame, values 0-1000 separated by ';'.
    """

    @Signal
    def frame(self) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bars: list[float] = [0.0] * CAVA_BARS
        self.available = GLib.find_program_in_path("cava") is not None
        self._process: Gio.Subprocess | None = None
        self._stream: Gio.DataInputStream | None = None
        self._cancellable: Gio.Cancellable | None = None

    @property
    def running(self) -> bool:
        return self._process is not None

    def _write_config(self):
        os.makedirs(os.path.dirname(CAVA_CONFIG), exist_ok=True)
        with open(CAVA_CONFIG, "w") as f:
            f.write(
                f"""[general]
bars = {CAVA_BARS}
framerate = 30
autosens = 1

[input]
method = pulse
source = auto

[output]
method = raw
raw_target = /dev/stdout
data_format = ascii
ascii_max_range = 1000
bar_delimiter = 59
frame_delimiter = 10

[smoothing]
noise_reduction = 77
"""
            )

    def start(self):
        if self.running or not self.available:
            return
        try:
            self._write_config()
            self._process = Gio.Subprocess.new(
                ["cava", "-p", CAVA_CONFIG],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE,
            )
        except (GLib.Error, OSError) as e:
            logger.warning(f"[Desktop] Couldn't start cava: {e}")
            self.available = False
            self._process = None
            return
        pipe = self._process.get_stdout_pipe()
        if pipe is None:
            self.stop()
            return
        self._stream = Gio.DataInputStream.new(pipe)
        self._cancellable = Gio.Cancellable()
        self._read_next()

    def stop(self):
        if self._cancellable is not None:
            self._cancellable.cancel()
        if self._process is not None:
            self._process.force_exit()
        self._process = None
        self._stream = None
        self._cancellable = None
        self.bars = [0.0] * CAVA_BARS
        self.frame()

    def _read_next(self):
        if self._stream is None:
            return
        self._stream.read_line_async(
            GLib.PRIORITY_DEFAULT, self._cancellable, self._on_line
        )

    def _on_line(self, stream: Gio.DataInputStream, result: Gio.AsyncResult):
        try:
            line, _length = stream.read_line_finish_utf8(result)
        except GLib.Error:
            return  # cancelled or the process went away
        if line is None:
            self.stop()
            return
        values = [v for v in line.split(";") if v]
        if len(values) >= CAVA_BARS:
            try:
                self.bars = [int(v) / 1000 for v in values[:CAVA_BARS]]
            except ValueError:
                pass
            self.frame()
        self._read_next()


# Particles


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    size: float
    phase: float
    spin: float
    color: tuple[float, float, float]


_LEAF_COLORS = [
    (0.85, 0.45, 0.15),
    (0.75, 0.25, 0.12),
    (0.9, 0.65, 0.2),
    (0.55, 0.3, 0.12),
]
_PETAL_COLORS = [(1.0, 0.75, 0.82), (0.98, 0.85, 0.9), (1.0, 0.65, 0.75)]


def season_mode(now: datetime.datetime, is_night: bool) -> str:
    """The particle mode "auto" resolves to for this date and time."""
    month = now.month
    if month in (12, 1, 2):
        return "snow"
    if month in (3, 4, 5):
        return "petals"
    if month in (9, 10, 11):
        return "leaves"
    return "fireflies" if is_night else "off"


class ParticleField:
    def __init__(self):
        self.mode = "off"
        self.particles: list[Particle] = []
        self._size = (0, 0)

    def configure(self, mode: str, width: int, height: int):
        if mode == self.mode and (width, height) == self._size:
            return
        self.mode, self._size = mode, (width, height)
        count = {
            "snow": width * height // 30000,
            "leaves": width * height // 90000,
            "petals": width * height // 80000,
            "fireflies": width * height // 70000,
        }.get(mode, 0)
        self.particles = [
            self._spawn(width, height, anywhere=True) for _ in range(count)
        ]

    def _spawn(self, width: int, height: int, anywhere: bool = False) -> Particle:
        rnd = random.random
        x = rnd() * width
        y = rnd() * height if anywhere else -20.0
        match self.mode:
            case "snow":
                size = 1.2 + rnd() * 2.8
                return Particle(
                    x, y, 0, 15 + size * 10, size, rnd() * 6.3, 0, (1, 1, 1)
                )
            case "leaves":
                return Particle(
                    x, y, 10 * (rnd() - 0.3), 30 + rnd() * 35, 6 + rnd() * 6,
                    rnd() * 6.3, (rnd() - 0.5) * 2, random.choice(_LEAF_COLORS),
                )  # fmt: skip
            case "petals":
                return Particle(
                    x, y, 15 * rnd(), 22 + rnd() * 25, 4 + rnd() * 4,
                    rnd() * 6.3, (rnd() - 0.5) * 2.5, random.choice(_PETAL_COLORS),
                )  # fmt: skip
            case _:  # fireflies wander anywhere in the lower part of the screen
                return Particle(
                    x, height * (0.35 + rnd() * 0.6), 0, 0, 1.5 + rnd() * 1.5,
                    rnd() * 6.3, rnd() * 6.3, (1.0, 0.92, 0.45),
                )  # fmt: skip

    def step(self, dt: float, t: float):
        width, height = self._size
        for i, p in enumerate(self.particles):
            if self.mode == "fireflies":
                p.spin += (random.random() - 0.5) * 2 * dt
                p.x += math.cos(p.spin) * 18 * dt
                p.y += math.sin(p.spin) * 12 * dt
                if not (0 < p.x < width and height * 0.25 < p.y < height):
                    p.spin += math.pi
                continue
            sway = math.sin(t * 0.8 + p.phase) * (25 if self.mode == "snow" else 40)
            p.x += (p.vx + sway) * dt
            p.y += p.vy * dt
            p.phase += p.spin * dt
            if p.y > height + 20 or p.x < -40 or p.x > width + 40:
                self.particles[i] = self._spawn(width, height)

    def draw(self, cr: cairo.Context, t: float):
        for p in self.particles:
            match self.mode:
                case "snow":
                    cr.set_source_rgba(1, 1, 1, 0.55 + p.size / 12)
                    cr.arc(p.x, p.y, p.size, 0, 2 * math.pi)
                    cr.fill()
                case "leaves" | "petals":
                    cr.save()
                    cr.translate(p.x, p.y)
                    cr.rotate(p.phase)
                    cr.scale(1, 0.5 + 0.3 * math.sin(p.phase * 1.7))
                    cr.arc(0, 0, p.size, 0, 2 * math.pi)
                    cr.restore()
                    cr.set_source_rgba(*p.color, 0.8)
                    cr.fill()
                case "fireflies":
                    glow = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * 2 + p.phase))
                    radius = p.size * 5
                    gradient = cairo.RadialGradient(p.x, p.y, 0, p.x, p.y, radius)
                    gradient.add_color_stop_rgba(0, *p.color, 0.9 * glow)
                    gradient.add_color_stop_rgba(0.25, *p.color, 0.35 * glow)
                    gradient.add_color_stop_rgba(1, *p.color, 0)
                    cr.set_source(gradient)
                    cr.arc(p.x, p.y, radius, 0, 2 * math.pi)
                    cr.fill()


# Prayer arc

PRAYERS = ("Fajr", "Dhuhr", "Asr", "Maghrib", "Isha")


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")[:2]
    return int(hours) * 60 + int(minutes)


class FxLayer(Gtk.DrawingArea):
    """One per monitor; the window feeds it state and decides when it runs."""

    def __init__(self, cava: Cava):
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.cava = cava
        self.particles = ParticleField()
        self.prayer_times: dict[str, str] = {}
        self.show_arc = True
        self.show_bars = False
        self.ink = (1.0, 1.0, 1.0)
        self.label_font = "Inter"
        self._bars = [0.0] * CAVA_BARS  # eased copy of cava's levels
        self._tick_id: int | None = None
        self._last: float | None = None
        self._t = 0.0
        self.connect("draw", self._on_draw)

    # Animation

    def set_animating(self, animating: bool):
        if animating and self._tick_id is None:
            self._last = None
            self._tick_id = GLib.timeout_add(FRAME_MS, self._tick)
        elif not animating and self._tick_id is not None:
            GLib.source_remove(self._tick_id)
            self._tick_id = None
            # don't leave the bars frozen mid-air
            self._bars = [0.0] * CAVA_BARS
            self.queue_draw()

    def _tick(self):
        now = GLib.get_monotonic_time() / 1_000_000
        dt = min(0.1, now - self._last) if self._last is not None else FRAME_MS / 1000
        self._last = now
        self._t += dt
        self.particles.step(dt, self._t)
        # rise quickly, fall gently
        target = self.cava.bars if self.show_bars else [0.0] * CAVA_BARS
        self._bars = [
            b + (v - b) * (0.6 if v > b else 0.15) for b, v in zip(self._bars, target)
        ]
        self.queue_draw()
        return True

    def configure_particles(self, mode: str):
        self.particles.configure(
            mode, self.get_allocated_width(), self.get_allocated_height()
        )

    # Drawing

    def _on_draw(self, widget: Gtk.Widget, cr: cairo.Context):
        w, h = widget.get_allocated_width(), widget.get_allocated_height()
        if self.particles.mode != "off":
            self.particles.draw(cr, self._t)
        if self.show_arc and self.prayer_times:
            self._draw_arc(cr, w, h)
        if any(b > 0.01 for b in self._bars):
            self._draw_bars(cr, w, h)
        return False

    def _arc_point(self, w: int, h: int, t: float) -> tuple[float, float]:
        # quadratic curve: a wide sun path rising from the lower corners,
        # clear of the clock at the top and the visualizer at the bottom
        x0, y0 = w * 0.06, h * 0.84
        x1, y1 = w / 2, h * 0.36
        x2, y2 = w * 0.94, h * 0.84
        u = 1 - t
        return (
            u * u * x0 + 2 * u * t * x1 + t * t * x2,
            u * u * y0 + 2 * u * t * y1 + t * t * y2,
        )

    def _draw_arc(self, cr: cairo.Context, w: int, h: int):
        try:
            marks = {name: _minutes(self.prayer_times[name]) for name in PRAYERS}
        except (KeyError, ValueError):
            return
        start, end = marks["Fajr"], marks["Isha"]
        if end <= start:
            return
        now = datetime.datetime.now()
        current = (now.hour * 60 + now.minute - start) / (end - start)

        def path(t0: float, t1: float, steps: int = 80):
            cr.new_path()
            for i in range(steps + 1):
                cr.line_to(*self._arc_point(w, h, t0 + (t1 - t0) * i / steps))

        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(1.5)
        path(0, 1)
        cr.set_source_rgba(*self.ink, 0.18)
        cr.stroke()
        if current > 0:
            path(0, min(1.0, current))
            cr.set_source_rgba(*self.ink, 0.45)
            cr.stroke()

        cr.select_font_face(
            self.label_font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL
        )
        cr.set_font_size(max(11, h * 0.011))
        for name, minute in marks.items():
            x, y = self._arc_point(w, h, (minute - start) / (end - start))
            cr.arc(x, y, 3, 0, 2 * math.pi)
            cr.set_source_rgba(*self.ink, 0.5)
            cr.fill()
            extents = cr.text_extents(name)
            cr.move_to(x - extents.width / 2, y + 18 + extents.height)
            cr.set_source_rgba(*self.ink, 0.45)
            cr.show_text(name)

        if 0 <= current <= 1:
            x, y = self._arc_point(w, h, current)
            glow = cairo.RadialGradient(x, y, 0, x, y, 22)
            glow.add_color_stop_rgba(0, *self.ink, 0.35)
            glow.add_color_stop_rgba(1, *self.ink, 0)
            cr.set_source(glow)
            cr.arc(x, y, 22, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgba(*self.ink, 0.95)
            cr.arc(x, y, 6, 0, 2 * math.pi)
            cr.fill()

    def _draw_bars(self, cr: cairo.Context, w: int, h: int):
        count = len(self._bars)
        slot = w / count
        width = slot * 0.45
        max_height = h * 0.08
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(width)
        for i, level in enumerate(self._bars):
            if level <= 0.01:
                continue
            x = slot * (i + 0.5)
            top = h - 6 - level * max_height
            cr.move_to(x, h - 6)
            cr.line_to(x, top)
            cr.set_source_rgba(*self.ink, 0.15 + 0.3 * level)
            cr.stroke()
