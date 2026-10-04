"""
Prayer extras: the Qibla direction, the adhan at prayer time, and Ramadan's
Iftar / Suhoor countdowns.

The adhan is your own recording: put it at ~/.local/share/fabric/adhan.mp3
(and optionally adhan-fajr.mp3 for Fajr). Without one, a soft chime plays.
"""

import datetime
import json
import math
import os

import cairo
from fabric.utils import get_relative_path
from gi.repository import Gio, GLib, Gtk
from loguru import logger

from fabric_config.utils.process import run_command_async

KAABA = (21.4225, 39.8262)
DATA_DIR = os.path.join(GLib.get_user_data_dir(), "fabric")
SETTINGS_FILE = os.path.join(
    GLib.get_user_cache_dir(), "fabric", "prayer-times", "settings.json"
)
CHIME = get_relative_path("../../../assets/sounds/notification.mp3")
RAMADAN = 9

_COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


# Qibla


def qibla_bearing(lat: float, lon: float) -> float:
    """Initial great-circle bearing to the Kaaba, degrees clockwise from north."""
    p1, p2 = math.radians(lat), math.radians(KAABA[0])
    dlon = math.radians(KAABA[1] - lon)
    y = math.sin(dlon) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    return math.degrees(math.atan2(y, x)) % 360


def compass_point(bearing: float) -> str:
    return _COMPASS[round(bearing / 45) % 8]


class QiblaCompass(Gtk.DrawingArea):
    """A small dial with north at the top and a needle towards the Qibla."""

    def __init__(self, size: int = 56):
        super().__init__()
        self.set_name("qibla-compass")
        self.set_size_request(size, size)
        self.set_valign(Gtk.Align.CENTER)
        self.bearing: float | None = None
        self.connect("draw", self._on_draw)
        self.show()

    def set_bearing(self, bearing: float | None):
        self.bearing = bearing
        self.queue_draw()

    def _on_draw(self, _widget, cr: cairo.Context):
        style = self.get_style_context()
        fg = style.get_color(Gtk.StateFlags.NORMAL)
        size = min(self.get_allocated_width(), self.get_allocated_height())
        c, r = size / 2, size / 2 - 2

        # dial and ticks
        cr.set_line_width(1.2)
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.25)
        cr.arc(c, c, r, 0, math.tau)
        cr.stroke()
        for i in range(8):
            angle = math.radians(i * 45) - math.pi / 2
            inner = r - (5 if i % 2 == 0 else 3)
            cr.move_to(c + inner * math.cos(angle), c + inner * math.sin(angle))
            cr.line_to(c + r * math.cos(angle), c + r * math.sin(angle))
        cr.stroke()

        # N
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.6)
        cr.select_font_face("Inter", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(max(8, size * 0.16))
        ext = cr.text_extents("N")
        cr.move_to(c - ext.width / 2 - ext.x_bearing, c - r + 8 + ext.height)
        cr.show_text("N")

        if self.bearing is None:
            return
        # needle: accent towards the Qibla, faint tail
        accent = style.lookup_color("accent")
        rgb = (
            (accent[1].red, accent[1].green, accent[1].blue)
            if accent[0]
            else (fg.red, fg.green, fg.blue)
        )
        angle = math.radians(self.bearing) - math.pi / 2
        tip = (c + (r - 6) * math.cos(angle), c + (r - 6) * math.sin(angle))
        tail = (c - r * 0.35 * math.cos(angle), c - r * 0.35 * math.sin(angle))
        side = angle + math.pi / 2
        half = size * 0.06
        cr.move_to(*tip)
        cr.line_to(c + half * math.cos(side), c + half * math.sin(side))
        cr.line_to(*tail)
        cr.line_to(c - half * math.cos(side), c - half * math.sin(side))
        cr.close_path()
        cr.set_source_rgba(*rgb, 0.95)
        cr.fill()
        cr.arc(c, c, 2.2, 0, math.tau)
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.9)
        cr.fill()


# Settings


def load_settings() -> dict:
    try:
        with open(SETTINGS_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict):
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f)
    except OSError as e:
        logger.warning(f"[Prayer] Couldn't save settings: {e}")


# Adhan


def adhan_file(prayer: str) -> str | None:
    """Your recording for this prayer, if there is one."""
    candidates = [f"adhan-{prayer.lower()}.mp3", "adhan.mp3"]
    for name in candidates:
        path = os.path.join(DATA_DIR, name)
        if os.path.isfile(path):
            return path
    return None


class AdhanPlayer:
    """Plays one sound at a time with sox's `play`; stop() cuts it short."""

    def __init__(self):
        self._process: Gio.Subprocess | None = None

    @property
    def playing(self) -> bool:
        return self._process is not None

    def play(self, prayer: str):
        self.stop()
        path = adhan_file(prayer)
        if path is None:
            logger.info(
                f"[Prayer] No adhan recording in {DATA_DIR} (adhan.mp3); chiming"
            )
            path = CHIME
        try:
            process = Gio.Subprocess.new(
                ["play", "-q", path],
                Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE,
            )
        except GLib.Error as e:
            logger.error(f"[Prayer] Couldn't play {path}: {e.message}")
            return
        self._process = process

        def done(proc: Gio.Subprocess, result: Gio.AsyncResult):
            try:
                proc.wait_finish(result)
            except GLib.Error:
                pass
            if proc is self._process:
                self._process = None

        process.wait_async(None, done)

    def stop(self):
        if self._process is not None:
            self._process.force_exit()
            self._process = None


def notify(title: str, body: str):
    run_command_async(
        [
            "notify-send",
            "-a",
            "Prayer Times",
            "-i",
            "preferences-system-time",
            title,
            body,
        ]
    )


# Ramadan


def ramadan_countdown(
    times: dict[str, str], hijri_month: int | None, now: datetime.datetime
) -> str | None:
    """
    During Ramadan, "Iftar in 2h 13m" between Fajr and Maghrib and "Suhoor
    ends in 5h 2m" through the night; None otherwise.
    """
    if hijri_month != RAMADAN or "Fajr" not in times or "Maghrib" not in times:
        return None

    def at(hhmm: str) -> datetime.datetime:
        hour, minute = (int(v) for v in hhmm.split(":")[:2])
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    fajr, maghrib = at(times["Fajr"]), at(times["Maghrib"])
    if fajr <= now < maghrib:
        label, target = "Iftar in", maghrib
    else:
        label = "Suhoor ends in"
        target = fajr if now < fajr else fajr + datetime.timedelta(days=1)
    minutes = int((target - now).total_seconds() // 60)
    hours, minutes = divmod(minutes, 60)
    return f"{label} {hours}h {minutes}m" if hours else f"{label} {minutes}m"
