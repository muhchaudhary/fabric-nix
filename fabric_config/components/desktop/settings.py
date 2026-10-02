"""
Desktop settings, shared by every monitor and saved between restarts.

Everything on the desktop can be switched on or off from its right-click
menu; this is where those choices live. Older files (just "24h" and "face")
still load.
"""

import json
import os
from typing import Literal

from gi.repository import GLib
from loguru import logger

SETTINGS_FILE = os.path.join(GLib.get_user_cache_dir(), "fabric", "desktop_clock.json")

FACES = ("digital", "analog", "words")
PARTICLE_MODES = ("auto", "snow", "leaves", "petals", "fireflies", "off")
Position = Literal["top", "center", "bottom-left", "bottom-right"]
POSITIONS: tuple[Position, ...] = ("top", "center", "bottom-left", "bottom-right")

# widget id -> (menu label, on by default)
WIDGETS: dict[str, tuple[str, bool]] = {
    "prayer": ("Next prayer", True),
    "now_playing": ("Now playing", True),
    "weather": ("Weather", True),
    "hijri": ("Hijri date", True),
    "greeting": ("Greeting", True),
    "on_this_day": ("On this day", True),
    "prayer_arc": ("Prayer arc", True),
    "visualizer": ("Audio visualizer", True),
    "notes": ("Sticky notes", True),
    "moods": ("Clock moods", True),
}


class DesktopSettings:
    def __init__(self):
        self.use_24h = False
        self.face = FACES[0]
        self.particles = "auto"
        self.position: Position = "top"
        self.widgets = {name: default for name, (_, default) in WIDGETS.items()}
        try:
            with open(SETTINGS_FILE) as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        self.use_24h = bool(data.get("24h", False))
        if data.get("face") in FACES:
            self.face = data["face"]
        if data.get("particles") in PARTICLE_MODES:
            self.particles = data["particles"]
        if data.get("position") in POSITIONS:
            self.position = data["position"]
        saved = data.get("widgets")
        if isinstance(saved, dict):
            for name in self.widgets:
                if isinstance(saved.get(name), bool):
                    self.widgets[name] = saved[name]

    def enabled(self, widget: str) -> bool:
        return self.widgets.get(widget, False)

    def save(self):
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            tmp = SETTINGS_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(
                    {
                        "24h": self.use_24h,
                        "face": self.face,
                        "particles": self.particles,
                        "position": self.position,
                        "widgets": self.widgets,
                    },
                    f,
                )
            os.replace(tmp, SETTINGS_FILE)
        except OSError as e:
            logger.warning(f"[Desktop] Couldn't save settings: {e}")
