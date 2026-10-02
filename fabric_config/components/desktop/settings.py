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
Position = Literal["top", "center", "bottom-left", "bottom-right"]
POSITIONS: tuple[Position, ...] = ("top", "center", "bottom-left", "bottom-right")

# widget id -> (menu label, on by default)
WIDGETS: dict[str, tuple[str, bool]] = {
    "prayer": ("Next prayer", True),
    "lyrics": ("Lyrics", True),
    "retro_player": ("Retro player", True),
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
        self.position: Position = "top"
        # shared defaults, and per-monitor choices that override them
        self.widgets = {name: default for name, (_, default) in WIDGETS.items()}
        self.monitor_widgets: dict[str, dict[str, bool]] = {}
        self.player_theme = "mp3"
        # monitor name -> [x, y] of the retro player
        self.player_positions: dict[str, list[int]] = {}
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
        if data.get("position") in POSITIONS:
            self.position = data["position"]
        if isinstance(data.get("player_theme"), str):
            self.player_theme = data["player_theme"]
        positions = data.get("player_positions")
        if isinstance(positions, dict):
            self.player_positions = {
                str(k): [int(v[0]), int(v[1])]
                for k, v in positions.items()
                if isinstance(v, list) and len(v) == 2
            }
        per_monitor = data.get("monitor_widgets")
        if isinstance(per_monitor, dict):
            self.monitor_widgets = {
                str(monitor): {
                    name: value
                    for name, value in choices.items()
                    if name in WIDGETS and isinstance(value, bool)
                }
                for monitor, choices in per_monitor.items()
                if isinstance(choices, dict)
            }
        saved = data.get("widgets")
        if isinstance(saved, dict):
            for name in self.widgets:
                if isinstance(saved.get(name), bool):
                    self.widgets[name] = saved[name]

    def enabled(self, widget: str, monitor: str | None = None) -> bool:
        """Whether `widget` shows, on `monitor` if given (its own choice wins)."""
        if monitor is not None:
            choice = self.monitor_widgets.get(monitor, {}).get(widget)
            if choice is not None:
                return choice
        return self.widgets.get(widget, False)

    def set_widget(self, widget: str, monitor: str, value: bool):
        self.monitor_widgets.setdefault(monitor, {})[widget] = value

    def use_everywhere(self, monitor: str):
        """Make `monitor`'s choices the defaults and drop every override."""
        self.widgets = {name: self.enabled(name, monitor) for name in WIDGETS}
        self.monitor_widgets = {}

    def save(self):
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            tmp = SETTINGS_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(
                    {
                        "24h": self.use_24h,
                        "face": self.face,
                        "position": self.position,
                        "widgets": self.widgets,
                        "monitor_widgets": self.monitor_widgets,
                        "player_theme": self.player_theme,
                        "player_positions": self.player_positions,
                    },
                    f,
                )
            os.replace(tmp, SETTINGS_FILE)
        except OSError as e:
            logger.warning(f"[Desktop] Couldn't save settings: {e}")
