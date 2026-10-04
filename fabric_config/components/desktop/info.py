"""
Small pieces of information shown under the desktop clock: weather, Hijri
date, a greeting and an "on this day" line. Network and disk work runs off
the main thread; results come back on the GTK loop.
"""

import datetime
import json
import os
import random
import threading
from collections.abc import Callable
from dataclasses import dataclass

from fabric.core.service import Service, Signal
from gi.repository import GLib
from loguru import logger

CACHE_DIR = os.path.join(GLib.get_user_cache_dir(), "fabric")
PRAYER_TIMES_FILE = os.path.join(CACHE_DIR, "prayer-times", "current_times.json")
LOCATION_FILE = os.path.join(CACHE_DIR, "prayer-times", "location.json")
VERSE_CACHE = os.path.join(CACHE_DIR, "desktop_verse.json")
QUOTES_FILE = os.path.join(GLib.get_user_config_dir(), "fabric", "quotes.txt")
PICTURES_DIR = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES) or (
    os.path.expanduser("~/Pictures")
)

WEATHER_REFRESH_S = 30 * 60
ON_THIS_DAY_ROTATE_S = 20 * 60
PHOTO_SCAN_LIMIT = 20000
QURAN_AYAHS = 6236


def _in_thread(work: Callable[[], object], done: Callable[[object], None]):
    def run():
        try:
            result = work()
        except Exception as e:
            logger.warning(f"[Desktop] {e}")
            result = None
        GLib.idle_add(lambda: done(result) or False)

    threading.Thread(target=run, daemon=True).start()


def _location() -> tuple[float, float] | None:
    """The location the prayer-times service already looked up."""
    try:
        with open(LOCATION_FILE) as f:
            data = json.load(f)
        return float(data["lat"]), float(data["lon"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


# Weather (Open-Meteo: free, no key)

_WEATHER_CODES = {
    0: "Clear",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Cloudy",
    45: "Fog",
    48: "Fog",
    51: "Drizzle",
    53: "Drizzle",
    55: "Drizzle",
    56: "Freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Showers",
    81: "Showers",
    82: "Heavy showers",
    85: "Snow showers",
    86: "Snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm",
    99: "Thunderstorm",
}


class WeatherService(Service):
    @Signal
    def changed(self) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.text: str | None = None
        # for the drawn weather: WMO code, day or night, wind in km/h
        self.code: int | None = None
        self.is_day = True
        self.wind = 0.0
        self.refresh()
        GLib.timeout_add_seconds(WEATHER_REFRESH_S, lambda: self.refresh() or True)

    def refresh(self):
        location = _location()
        if location is None:
            return
        lat, lon = location

        def fetch():
            import requests

            response = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,weather_code,is_day,wind_speed_10m",
                    "timezone": "auto",
                },
                timeout=10,
            )
            response.raise_for_status()
            current = response.json()["current"]
            code = int(current["weather_code"])
            condition = _WEATHER_CODES.get(code, "")
            return (
                f"{round(current['temperature_2m'])}° {condition}".strip(),
                code,
                bool(current.get("is_day", 1)),
                float(current.get("wind_speed_10m") or 0.0),
            )

        def done(result):
            if not result:
                return
            text, code, is_day, wind = result
            if (text, code, is_day) != (self.text, self.code, self.is_day):
                self.text, self.code, self.is_day, self.wind = (
                    text,
                    code,
                    is_day,
                    wind,
                )
                self.changed()

        _in_thread(fetch, done)


# Hijri date (from the prayer-times cache, which the API fills daily)


def hijri_date() -> str | None:
    try:
        with open(PRAYER_TIMES_FILE) as f:
            hijri = json.load(f)["date"]["hijri"]
        return f"{int(hijri['day'])} {hijri['month']['en']} {hijri['year']}"
    except (OSError, ValueError, KeyError, TypeError):
        return None


# Greeting


def greeting(now: datetime.datetime | None = None) -> str:
    hour = (now or datetime.datetime.now()).hour
    if 5 <= hour < 12:
        part = "Good morning"
    elif 12 <= hour < 17:
        part = "Good afternoon"
    elif 17 <= hour < 22:
        part = "Good evening"
    else:
        part = "Good night"
    real_name = GLib.get_real_name()
    name = (
        real_name.split()[0]
        if real_name and real_name != "Unknown"
        else GLib.get_user_name().capitalize()
    )
    return f"{part}, {name}"


# On this day: a verse of the day, your own quotes, and photos from this date


@dataclass
class Memory:
    text: str
    path: str | None = None  # a photo to open on click


class OnThisDay(Service):
    @Signal
    def changed(self) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current: Memory | None = None
        self._items: list[Memory] = []
        self._day: datetime.date | None = None
        self.refresh()
        GLib.timeout_add_seconds(ON_THIS_DAY_ROTATE_S, lambda: self.rotate() or True)

    def refresh(self):
        today = datetime.date.today()
        if self._day == today:
            return
        self._day = today
        self._items = [Memory(q) for q in self._quotes()]
        self.rotate()

        def gather():
            items = []
            if verse := self._verse_of_the_day(today):
                items.append(Memory(verse))
            items += self._photo_memories(today)
            return items

        def done(items):
            if items:
                self._items += list(items)  # type: ignore[arg-type]
                self.rotate()

        _in_thread(gather, done)

    def rotate(self):
        if not self._items:
            return
        choices = [m for m in self._items if m != self.current] or self._items
        self.current = random.choice(choices)
        self.changed()

    @staticmethod
    def _quotes() -> list[str]:
        try:
            with open(QUOTES_FILE) as f:
                return [line.strip() for line in f if line.strip()]
        except OSError:
            return []

    @staticmethod
    def _verse_of_the_day(today: datetime.date) -> str | None:
        try:
            with open(VERSE_CACHE) as f:
                cached = json.load(f)
            if cached.get("date") == today.isoformat():
                return cached["text"]
        except (OSError, ValueError, KeyError):
            pass
        import requests

        number = random.Random(today.toordinal()).randint(1, QURAN_AYAHS)
        response = requests.get(
            f"https://api.alquran.cloud/v1/ayah/{number}/en.sahih", timeout=10
        )
        response.raise_for_status()
        data = response.json()["data"]
        text = f"“{data['text']}” — {data['surah']['englishName']} {data['surah']['number']}:{data['numberInSurah']}"
        try:
            with open(VERSE_CACHE, "w") as f:
                json.dump({"date": today.isoformat(), "text": text}, f)
        except OSError:
            pass
        return text

    @staticmethod
    def _photo_memories(today: datetime.date) -> list[Memory]:
        if not os.path.isdir(PICTURES_DIR):
            return []
        found: dict[int, str] = {}
        scanned = 0
        for root, _dirs, files in os.walk(PICTURES_DIR):
            for name in files:
                if not name.lower().endswith(
                    (".jpg", ".jpeg", ".png", ".heic", ".webp")
                ):
                    continue
                scanned += 1
                if scanned > PHOTO_SCAN_LIMIT:
                    break
                path = os.path.join(root, name)
                try:
                    taken = datetime.date.fromtimestamp(os.path.getmtime(path))
                except OSError:
                    continue
                if (taken.month, taken.day) == (
                    today.month,
                    today.day,
                ) and taken.year < today.year:
                    found.setdefault(today.year - taken.year, path)
        memories = []
        for years, path in sorted(found.items()):
            label = "1 year" if years == 1 else f"{years} years"
            memories.append(Memory(f"A photo from {label} ago today", path))
        return memories
