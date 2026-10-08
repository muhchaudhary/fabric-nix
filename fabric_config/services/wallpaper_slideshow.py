"""
Wallpaper slideshow: a new wallpaper from ~/wallpapers every so often, on
every monitor.

With "day and night" on, it picks from the brighter half of the collection
between sunrise and sunset and the darker half otherwise (sunrise and sunset
come from the prayer-times data). Each wallpaper's brightness is measured once
(Pillow, at thumbnail size, off the main thread) and cached by path and mtime.
"""

import datetime
import json
import os
import random
import time

from fabric.core.service import Property, Service
from gi.repository import GLib
from loguru import logger

from fabric_config.utils import image_worker
from fabric_config.utils.wallpaper import (
    WALLPAPER_DIR,
    apply_wallpaper,
    get_last_wallpaper,
    list_monitors,
    list_wallpapers,
    save_wallpaper,
)

CACHE = os.path.join(GLib.get_user_cache_dir(), "fabric", "wallpaper-picker")
SETTINGS_FILE = os.path.join(CACHE, "slideshow.json")
BRIGHTNESS_FILE = os.path.join(CACHE, "brightness.json")
PRAYER_TIMES_FILE = os.path.join(
    GLib.get_user_cache_dir(), "fabric", "prayer-times", "current_times.json"
)
INTERVALS = (15, 30, 60, 180)  # minutes
CHECK_S = 60


class WallpaperSlideshow(Service):
    def __init__(self, **kwargs):
        self._enabled = False
        self._interval = 60
        self._day_night = True
        self._last_change = 0.0
        # wallpapers still to show this round, so none repeats too soon
        self._queue: list[str] = []
        self._brightness: dict[str, list[float]] = {}  # path -> [mtime, value]
        self._measuring = False
        self._was_day: bool | None = None
        try:
            with open(SETTINGS_FILE) as f:
                data = json.load(f)
            self._enabled = bool(data.get("enabled", False))
            if data.get("interval") in INTERVALS:
                self._interval = data["interval"]
            self._day_night = bool(data.get("day_night", True))
            self._last_change = float(data.get("last_change", 0))
        except (OSError, ValueError, TypeError):
            pass
        try:
            with open(BRIGHTNESS_FILE) as f:
                self._brightness = json.load(f)
        except (OSError, ValueError):
            pass
        super().__init__(**kwargs)
        GLib.timeout_add_seconds(CHECK_S, self._check)
        if self._enabled:
            self._measure()

    # Settings

    @Property(bool, "read-write", default_value=False)
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        if value == self._enabled:
            return
        self._enabled = value
        self._save()
        if value:
            self._measure()
            # starting it shows something new now
            self.next()

    @Property(int, "read-write", default_value=60)
    def interval(self) -> int:
        """Minutes between wallpapers."""
        return self._interval

    @interval.setter
    def interval(self, value: int):
        self._interval = value
        self._save()

    @Property(bool, "read-write", default_value=True)
    def day_night(self) -> bool:
        return self._day_night

    @day_night.setter
    def day_night(self, value: bool):
        self._day_night = value
        self._queue = []
        self._save()

    def _save(self):
        try:
            os.makedirs(CACHE, exist_ok=True)
            with open(SETTINGS_FILE, "w") as f:
                json.dump(
                    {
                        "enabled": self._enabled,
                        "interval": self._interval,
                        "day_night": self._day_night,
                        "last_change": self._last_change,
                    },
                    f,
                )
        except OSError as e:
            logger.warning(f"[Slideshow] Couldn't save settings: {e}")

    # Choosing

    def _check(self) -> bool:
        if not self._enabled:
            return True
        due = time.time() - self._last_change >= self._interval * 60
        # at sunrise and sunset, move to a wallpaper that suits it (only
        # then: one picked by hand stays until the next turn)
        day = is_daytime()
        turned = self._was_day is not None and day != self._was_day
        self._was_day = day
        if due or (self._day_night and turned):
            self.next()
        return True

    def next(self):
        """Show the next wallpaper now."""
        path = self._pick()
        if path is None:
            logger.info(f"[Slideshow] No wallpapers in {WALLPAPER_DIR}")
            return
        logger.info(f"[Slideshow] {os.path.basename(path)}")
        save_wallpaper(path)
        apply_wallpaper(path, [m["name"] for m in list_monitors()])
        self._last_change = time.time()
        self._save()

    def _pick(self) -> str | None:
        paths = [os.path.join(WALLPAPER_DIR, n) for n in list_wallpapers()]
        if not paths:
            return None
        pool = [p for p in paths if self._suits_now(p)] or paths
        current = get_last_wallpaper()
        self._queue = [p for p in self._queue if p in pool]
        if not self._queue:
            self._queue = [p for p in pool if p != current] or pool
            random.shuffle(self._queue)
        return self._queue.pop()

    def _suits_now(self, path: str | None) -> bool:
        if not self._day_night or path is None:
            return True
        value = self._value(path)
        if value is None:
            return True  # not measured yet
        values = sorted(
            v
            for n in list_wallpapers()
            if (v := self._value(os.path.join(WALLPAPER_DIR, n))) is not None
        )
        if not values:
            return True
        median = values[len(values) // 2]
        return (value >= median) == is_daytime()

    def _value(self, path: str) -> float | None:
        entry = self._brightness.get(path)
        try:
            if entry and entry[0] == os.path.getmtime(path):
                return entry[1]
        except OSError:
            pass
        return None

    # Brightness

    def _measure(self):
        """Measure wallpapers not yet in the cache, on a thread."""
        if self._measuring:
            return
        todo = [
            os.path.join(WALLPAPER_DIR, n)
            for n in list_wallpapers()
            if self._value(os.path.join(WALLPAPER_DIR, n)) is None
        ]
        if not todo:
            return
        self._measuring = True

        def work():
            from PIL import Image, ImageStat

            results = {}
            for path in todo:
                try:
                    with Image.open(path) as image:
                        image.draft("L", (128, 128))
                        # shrink before converting (PNGs decode full size)
                        image.thumbnail((128, 128))
                        mean = ImageStat.Stat(image.convert("L")).mean[0] / 255
                    results[path] = [os.path.getmtime(path), mean]
                except Exception as e:
                    logger.debug(f"[Slideshow] Couldn't measure {path}: {e}")
            return results

        # one image at a time, with the other wallpaper decoding
        image_worker.submit(work, lambda results: self._measured(results or {}))

    def _measured(self, results: dict):
        self._measuring = False
        self._brightness.update(results)
        try:
            with open(BRIGHTNESS_FILE, "w") as f:
                json.dump(self._brightness, f)
        except OSError:
            pass


def is_daytime(now: datetime.datetime | None = None) -> bool:
    """Between today's sunrise and sunset (7:00-19:00 without prayer data)."""
    now = now or datetime.datetime.now()
    sunrise, sunset = "07:00", "19:00"
    try:
        with open(PRAYER_TIMES_FILE) as f:
            timings = json.load(f)["timings"]
        sunrise, sunset = timings["Sunrise"][:5], timings["Sunset"][:5]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    current = now.strftime("%H:%M")
    return sunrise <= current < sunset
