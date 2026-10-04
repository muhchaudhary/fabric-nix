"""
Weather drawn on the desktop: rain, snow, fog, a thunderstorm's lightning,
stars on a clear night. FxLayer steps and draws it under the prayer arc.

Positions are fractions of the screen, so a resize doesn't scatter anything;
sizes scale with the screen's height. Each kind draws in one or two cairo
paths, so a frame stays cheap.
"""

import math
import random

import cairo

# WMO weather codes (Open-Meteo) -> what's drawn
_KINDS = {
    **dict.fromkeys((2,), "partly-cloudy"),
    **dict.fromkeys((3,), "cloudy"),
    **dict.fromkeys((45, 48), "fog"),
    **dict.fromkeys((51, 53, 55, 56, 57), "drizzle"),
    **dict.fromkeys((61, 63, 66, 80, 81), "rain"),
    **dict.fromkeys((65, 67, 82), "heavy-rain"),
    **dict.fromkeys((71, 73, 77, 85), "snow"),
    **dict.fromkeys((75, 86), "heavy-snow"),
    **dict.fromkeys((95, 96, 99), "storm"),
}

KINDS = (
    "clear-night",
    "partly-cloudy",
    "cloudy",
    "fog",
    "drizzle",
    "rain",
    "heavy-rain",
    "snow",
    "heavy-snow",
    "storm",
)


def weather_kind(code: int | None, is_day: bool) -> str | None:
    """What to draw for a weather code; None for a clear day."""
    if code is None:
        return None
    if code in (0, 1):
        return None if is_day else "clear-night"
    return _KINDS.get(code)


# per kind: (raindrops, snowflakes, haze puffs). Haze costs a full-screen
# paint each frame, so falling weather goes without it
_AMOUNTS = {
    "clear-night": (0, 0, 0),
    "partly-cloudy": (0, 0, 3),
    "cloudy": (0, 0, 6),
    "fog": (0, 0, 9),
    "drizzle": (120, 0, 0),
    "rain": (240, 0, 0),
    "heavy-rain": (400, 0, 0),
    "snow": (0, 110, 0),
    "heavy-snow": (0, 220, 0),
    "storm": (380, 0, 0),
}

STARS = 70
HAZE_SCALE = 8


class WeatherParticles:
    def __init__(self, kind: str, wind_kmh: float = 0.0):
        self.kind = kind
        drops, flakes, puffs = _AMOUNTS[kind]
        # rain leans with the wind, up to about 30 degrees
        self.slant = max(-0.55, min(0.55, wind_kmh / 60))
        self.drops = [self._drop(random.random()) for _ in range(drops)]
        self.flakes = [self._flake(random.random()) for _ in range(flakes)]
        self.puffs = [self._puff(random.random()) for _ in range(puffs)]
        self.stars = (
            [
                # x, y, size, twinkle speed, phase
                (
                    random.random(),
                    random.random() * 0.5,
                    random.uniform(0.6, 1.6),
                    random.uniform(0.5, 1.8),
                    random.uniform(0, math.tau),
                )
                for _ in range(STARS)
            ]
            if kind == "clear-night"
            else []
        )
        # slow things (drifting haze, twinkling) don't need 30 fps
        self.frame_s = 1 / 30 if drops or flakes else 1 / 10
        self.t = 0.0
        self.flash = 0.0
        self._haze: cairo.ImageSurface | None = None
        self._next_flash = random.uniform(4, 10)

    # Particles: lists, mutated in place each step

    def _drop(self, y: float) -> list[float]:
        # x, y, speed (screen heights / s), length (screen heights), alpha
        heavy = self.kind in ("heavy-rain", "storm")
        light = self.kind == "drizzle"
        return [
            random.uniform(-0.2, 1.2),
            y,
            random.uniform(0.9, 1.5) * (0.7 if light else 1.0),
            random.uniform(0.012, 0.022) if light else random.uniform(0.02, 0.045),
            random.uniform(0.16, 0.36) if not heavy else random.uniform(0.2, 0.42),
        ]

    def _flake(self, y: float) -> list[float]:
        # x, y, speed, radius (screen heights), sway phase, alpha
        return [
            random.random(),
            y,
            random.uniform(0.035, 0.09),
            random.uniform(0.0012, 0.0032),
            random.uniform(0, math.tau),
            random.uniform(0.45, 0.9),
        ]

    def _puff(self, x: float) -> list[float]:
        # x, y, radius (screen heights), speed (screen widths / s), alpha
        fog = self.kind == "fog"
        return [
            x,
            random.uniform(0.1, 0.95) if fog else random.uniform(0.0, 0.35),
            random.uniform(0.25, 0.5),
            random.uniform(0.004, 0.012) * (1 if self.slant >= 0 else -1),
            random.uniform(0.07, 0.13) if fog else random.uniform(0.04, 0.08),
        ]

    def step(self, dt: float):
        self.t += dt
        for drop in self.drops:
            drop[1] += drop[2] * dt
            drop[0] += drop[2] * dt * self.slant * 0.56
            if drop[1] - drop[3] > 1:
                drop[:] = self._drop(-random.uniform(0, 0.1))
        for flake in self.flakes:
            flake[1] += flake[2] * dt
            flake[0] += math.sin(self.t * 0.8 + flake[4]) * 0.008 * dt
            if flake[1] > 1.02:
                flake[:] = self._flake(-0.02)
        for puff in self.puffs:
            puff[0] += puff[3] * dt
            if puff[0] > 1.5:
                puff[0] = -0.5
            elif puff[0] < -0.5:
                puff[0] = 1.5
        if self.kind == "storm":
            self.flash = max(0.0, self.flash - dt * 1.6)
            self._next_flash -= dt
            if self._next_flash <= 0:
                # a strike flickers: a bright flash, sometimes a second one
                self.flash = random.uniform(0.12, 0.22)
                self._next_flash = (
                    random.uniform(0.12, 0.25)
                    if random.random() < 0.4
                    else random.uniform(6, 16)
                )

    # Drawing

    def draw(self, cr: cairo.Context, w: int, h: int, ink: tuple[float, float, float]):
        cr.save()
        if self.puffs:
            self._draw_puffs(cr, w, h)
        if self.stars:
            self._draw_stars(cr, w, h)
        if self.drops:
            self._draw_drops(cr, w, h, ink)
        if self.flakes:
            self._draw_flakes(cr, w, h)
        if self.flash > 0:
            cr.set_source_rgba(0.85, 0.88, 1.0, self.flash)
            cr.paint()
        cr.restore()

    def _draw_puffs(self, cr: cairo.Context, w: int, h: int):
        # soft haze needs no detail: draw it at 1/8 size and scale it up
        # (full-size radial gradients this large cost ~10 ms each)
        sw, sh = max(1, w // HAZE_SCALE), max(1, h // HAZE_SCALE)
        if self._haze is None or self._haze.get_width() != sw:
            self._haze = cairo.ImageSurface(cairo.FORMAT_ARGB32, sw, sh)
        hz = cairo.Context(self._haze)
        hz.set_operator(cairo.OPERATOR_CLEAR)
        hz.paint()
        hz.set_operator(cairo.OPERATOR_OVER)
        for x, y, radius, _speed, alpha in self.puffs:
            cx, cy, r = x * sw, y * sh, radius * sh
            glow = cairo.RadialGradient(cx, cy, 0, cx, cy, r)
            glow.add_color_stop_rgba(0, 0.92, 0.93, 0.96, alpha)
            glow.add_color_stop_rgba(1, 0.92, 0.93, 0.96, 0)
            hz.set_source(glow)
            # squashed: clouds are wider than they're tall
            hz.save()
            hz.translate(cx, cy)
            hz.scale(1.8, 1.0)
            hz.translate(-cx, -cy)
            hz.arc(cx, cy, r, 0, math.tau)
            hz.restore()
            hz.fill()
        cr.save()
        cr.scale(w / sw, h / sh)
        cr.set_source_surface(self._haze, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_BILINEAR)
        cr.paint()
        cr.restore()

    def _draw_stars(self, cr: cairo.Context, w: int, h: int):
        scale = h / 1080
        for x, y, size, speed, phase in self.stars:
            twinkle = 0.5 + 0.5 * math.sin(self.t * speed + phase)
            cr.set_source_rgba(1, 1, 0.97, 0.25 + 0.6 * twinkle)
            cr.arc(x * w, y * h, size * scale * (0.7 + 0.5 * twinkle), 0, math.tau)
            cr.fill()

    def _draw_drops(
        self, cr: cairo.Context, w: int, h: int, ink: tuple[float, float, float]
    ):
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(max(1.0, h / 900))
        # drops in three alpha groups: three strokes instead of hundreds
        for low, high in ((0, 0.24), (0.24, 0.32), (0.32, 1)):
            cr.new_path()
            for x, y, _speed, length, alpha in self.drops:
                if not low <= alpha < high:
                    continue
                x0, y0 = x * w, y * h
                cr.move_to(x0, y0)
                cr.line_to(x0 - self.slant * length * h, y0 - length * h)
            cr.set_source_rgba(*ink, (low + high) / 2 if high < 1 else 0.38)
            cr.stroke()

    def _draw_flakes(self, cr: cairo.Context, w: int, h: int):
        for x, y, _speed, radius, _phase, alpha in self.flakes:
            cr.new_sub_path()
            cr.arc(x * w, y * h, max(1.0, radius * h), 0, math.tau)
            cr.set_source_rgba(1, 1, 1, alpha)
            cr.fill()
