"""
The desktop's drawn layer, under the clock: the prayer arc across the lower
half and the audio visualizer along the bottom.

It animates only while something is moving and the monitor's desktop is
showing; otherwise it redraws once a minute for the arc.
"""

import datetime
import math

import cairo
from gi.repository import GLib, Gtk

from fabric_config.services.cava import CAVA_BARS, Cava

FRAME_MS = 33  # ~30 fps
BARS_HEIGHT = 0.08  # tallest visualizer bar, as a fraction of the screen


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
        self.prayer_times: dict[str, str] = {}
        self.show_arc = True
        self.show_bars = False
        self.ink = (1.0, 1.0, 1.0)
        # a soft shadow behind the clock where the wallpaper is busy:
        # (x, y, width, height) of the clock, (r, g, b) and peak alpha
        self.scrim: (
            tuple[tuple[float, float, float, float], tuple[float, float, float], float]
            | None
        ) = None
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
        # rise quickly, fall gently
        target = self.cava.bars if self.show_bars else [0.0] * CAVA_BARS
        self._bars = [
            b + (v - b) * (0.6 if v > b else 0.15) for b, v in zip(self._bars, target)
        ]
        # only the bars move: repaint the strip along the bottom, not the
        # whole screen (which would repaint the clock and notes on top too)
        w, h = self.get_allocated_width(), self.get_allocated_height()
        strip = int(h * BARS_HEIGHT) + 16
        self.queue_draw_area(0, h - strip, w, strip)
        return True

    # Drawing

    def _on_draw(self, widget: Gtk.Widget, cr: cairo.Context):
        w, h = widget.get_allocated_width(), widget.get_allocated_height()
        if self.scrim is not None:
            self._draw_scrim(cr, *self.scrim)
        if self.show_arc and self.prayer_times:
            self._draw_arc(cr, w, h)
        if any(b > 0.01 for b in self._bars):
            self._draw_bars(cr, w, h)
        return False

    def _draw_scrim(
        self,
        cr: cairo.Context,
        rect: tuple[float, float, float, float],
        rgb: tuple[float, float, float],
        alpha: float,
    ):
        """
        A soft shadow (or light) behind the clock: a rounded rectangle whose
        edge fades out over `feather` pixels, like a large blurred
        box-shadow. It covers every line of the clock evenly and lifts the
        text off a busy wallpaper without a visible box. (Don't blur this
        layer in Hyprland: blur goes behind pixels above ignore_alpha, which
        would give it a hard edge.)
        """
        x, y, width, height = rect
        feather = min(width, height) * 0.3
        steps = 16
        # stacked layers, each a little smaller: their alphas compound to
        # `alpha` in the middle and fade smoothly towards the outside
        step_alpha = 1 - (1 - alpha) ** (1 / steps)
        cr.set_source_rgba(*rgb, step_alpha)
        for i in range(steps):
            grow = feather * (1 - i / steps) - feather * 0.35
            radius = max(8.0, grow + feather * 0.5)
            left, top = x - grow, y - grow
            right, bottom = x + width + grow, y + height + grow
            radius = min(radius, (right - left) / 2, (bottom - top) / 2)
            cr.new_sub_path()
            cr.arc(right - radius, top + radius, radius, -math.pi / 2, 0)
            cr.arc(right - radius, bottom - radius, radius, 0, math.pi / 2)
            cr.arc(left + radius, bottom - radius, radius, math.pi / 2, math.pi)
            cr.arc(left + radius, top + radius, radius, math.pi, 3 * math.pi / 2)
            cr.close_path()
            cr.fill()

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

    def _marks(self) -> tuple[dict[str, int], int, int] | None:
        """Each prayer's minute of the day, and the arc's first and last."""
        try:
            marks = {name: _minutes(self.prayer_times[name]) for name in PRAYERS}
        except (KeyError, ValueError):
            return None
        start, end = marks["Fajr"], marks["Isha"]
        return (marks, start, end) if end > start else None

    def _label_size(self, h: int) -> float:
        return max(13, h * 0.0145)

    def arc_obstacles(self, w: int, h: int) -> list[tuple[float, float, float, float]]:
        """
        Where the arc and its labels are drawn, as small rectangles along
        the curve with some room around them, for widgets to keep clear of.
        """
        if not self.show_arc or (found := self._marks()) is None:
            return []
        marks, start, end = found
        pad = max(16.0, h * 0.02)
        steps = 48
        rects = []
        for i in range(steps + 1):
            x, y = self._arc_point(w, h, i / steps)
            rects.append((x - pad, y - pad, 2 * pad, 2 * pad))
        font = self._label_size(h)
        label_w, label_h = font * 5, 18 + font * 1.6 + pad
        for minute in marks.values():
            x, y = self._arc_point(w, h, (minute - start) / (end - start))
            rects.append((x - label_w / 2, y, label_w, label_h))
        return rects

    def _draw_arc(self, cr: cairo.Context, w: int, h: int):
        if (found := self._marks()) is None:
            return
        marks, start, end = found
        now = datetime.datetime.now()
        current = (now.hour * 60 + now.minute - start) / (end - start)

        def path(t0: float, t1: float, steps: int = 80):
            cr.new_path()
            for i in range(steps + 1):
                cr.line_to(*self._arc_point(w, h, t0 + (t1 - t0) * i / steps))

        # It crosses the whole screen, over light and dark parts of the
        # wallpaper alike, so every stroke and label gets a soft halo in the
        # opposite tone (like map labels) and reads over either.
        halo = self._halo_rgb()
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)

        def stroke_with_halo(width: float, alpha: float):
            for halo_width, halo_alpha in ((width + 7, 0.3), (width + 3.5, 0.6)):
                cr.set_line_width(halo_width)
                cr.set_source_rgba(*halo, halo_alpha)
                cr.stroke_preserve()
            cr.set_line_width(width)
            cr.set_source_rgba(*self.ink, alpha)
            cr.stroke()

        path(0, 1)
        stroke_with_halo(1.5, 0.4)
        if current > 0:
            path(0, min(1.0, current))
            stroke_with_halo(2.5, 0.85)

        cr.select_font_face(
            self.label_font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD
        )
        cr.set_font_size(self._label_size(h))
        for name, minute in marks.items():
            x, y = self._arc_point(w, h, (minute - start) / (end - start))
            cr.new_path()
            cr.arc(x, y, 4, 0, 2 * math.pi)
            cr.set_source_rgba(*halo, 0.5)
            cr.set_line_width(4)
            cr.stroke_preserve()
            cr.set_source_rgba(*self.ink, 0.9)
            cr.fill()

            extents = cr.text_extents(name)
            cr.new_path()
            cr.move_to(
                x - extents.width / 2 - extents.x_bearing, y + 18 + extents.height
            )
            cr.text_path(name)
            for halo_width, halo_alpha in ((7, 0.35), (4, 0.75)):
                cr.set_line_width(halo_width)
                cr.set_source_rgba(*halo, halo_alpha)
                cr.stroke_preserve()
            cr.set_source_rgba(*self.ink, 0.9)
            cr.fill()

        if 0 <= current <= 1:
            x, y = self._arc_point(w, h, current)
            glow = cairo.RadialGradient(x, y, 0, x, y, 22)
            glow.add_color_stop_rgba(0, *self.ink, 0.35)
            glow.add_color_stop_rgba(1, *self.ink, 0)
            cr.set_source(glow)
            cr.arc(x, y, 22, 0, 2 * math.pi)
            cr.fill()
            cr.new_path()
            cr.arc(x, y, 6, 0, 2 * math.pi)
            cr.set_source_rgba(*halo, 0.6)
            cr.set_line_width(4)
            cr.stroke_preserve()
            cr.set_source_rgba(*self.ink, 0.95)
            cr.fill()

    def _halo_rgb(self) -> tuple[float, float, float]:
        """Near-white behind dark ink, near-black behind light ink."""
        r, g, b = self.ink
        if 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.5:
            return (0.98, 0.97, 0.95)
        return (0.04, 0.04, 0.07)

    def _draw_bars(self, cr: cairo.Context, w: int, h: int):
        count = len(self._bars)
        slot = w / count
        width = slot * 0.45
        max_height = h * BARS_HEIGHT
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
