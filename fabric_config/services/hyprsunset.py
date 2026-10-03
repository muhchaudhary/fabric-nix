"""
Night light through hyprsunset, driven over its IPC (`hyprctl hyprsunset ...`).

hyprsunset can't report whether it's filtering (an identity matrix still reads
back as its last temperature), so the on/off state, temperature and gamma live
here and are saved between restarts; on startup they're pushed to hyprsunset.
"""

import json
import os

from fabric.core.service import Property, Service
from gi.repository import GLib
from loguru import logger

from fabric_config.utils.process import run_command_async

SETTINGS_FILE = os.path.join(GLib.get_user_cache_dir(), "fabric", "hyprsunset.json")

MIN_TEMPERATURE = 2500
MAX_TEMPERATURE = 6500
MIN_GAMMA = 30
MAX_GAMMA = 100


class Hyprsunset(Service):
    def __init__(self, **kwargs):
        self._enabled = False
        self._temperature = 4000
        self._gamma = 100
        self._available = False
        # dragging a slider sets values many times a second; send one command
        # at a time, and only the latest state once the previous one is done
        self._busy = False
        self._dirty = False
        self._save_source: int | None = None

        try:
            with open(SETTINGS_FILE) as f:
                data = json.load(f)
            self._enabled = bool(data.get("enabled", False))
            self._temperature = _clamp(
                int(data.get("temperature", 4000)), MIN_TEMPERATURE, MAX_TEMPERATURE
            )
            self._gamma = _clamp(int(data.get("gamma", 100)), MIN_GAMMA, MAX_GAMMA)
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f"[Hyprsunset] Couldn't read settings: {e}")

        super().__init__(**kwargs)
        # probe the daemon; if it answers, bring it in line with our state
        run_command_async(["hyprctl", "hyprsunset", "temperature"], self._on_probe)

    @Property(bool, "readable", default_value=False)
    def available(self) -> bool:
        """Whether hyprsunset is running and answering."""
        return self._available

    @Property(bool, "read-write", default_value=False)
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        if value == self._enabled:
            return
        self._enabled = value
        self._changed("enabled")

    @Property(int, "read-write", default_value=4000)
    def temperature(self) -> int:
        return self._temperature

    @temperature.setter
    def temperature(self, value: int):
        value = _clamp(int(value), MIN_TEMPERATURE, MAX_TEMPERATURE)
        if value == self._temperature:
            return
        self._temperature = value
        self._changed("temperature")

    @Property(int, "read-write", default_value=100)
    def gamma(self) -> int:
        return self._gamma

    @gamma.setter
    def gamma(self, value: int):
        value = _clamp(int(value), MIN_GAMMA, MAX_GAMMA)
        if value == self._gamma:
            return
        self._gamma = value
        self._changed("gamma")

    def toggle(self):
        self.enabled = not self._enabled

    def _changed(self, prop: str):
        self.notify(prop)
        self._queue_save()
        self._dirty = True
        self._flush()

    def _on_probe(self, ok: bool, _stdout: str, stderr: str):
        if not ok:
            logger.warning(f"[Hyprsunset] Not available: {stderr.strip()}")
            return
        self._available = True
        self.notify("available")
        self._dirty = True
        self._flush()

    def _flush(self):
        if not self._available or self._busy or not self._dirty:
            return
        self._dirty = False
        self._busy = True
        if self._enabled:
            commands = [
                ["hyprctl", "hyprsunset", "temperature", str(self._temperature)],
                ["hyprctl", "hyprsunset", "gamma", str(self._gamma)],
            ]
        else:
            commands = [["hyprctl", "hyprsunset", "identity"]]
        self._run(commands)

    def _run(self, commands: list[list[str]]):
        def on_done(ok: bool, stdout: str, stderr: str):
            if not ok or stdout.strip() not in ("", "ok"):
                logger.error(
                    f"[Hyprsunset] {' '.join(commands[0][2:])}: "
                    f"{(stderr or stdout).strip()}"
                )
            if len(commands) > 1:
                self._run(commands[1:])
                return
            self._busy = False
            self._flush()

        run_command_async(commands[0], on_done)

    def _queue_save(self):
        if self._save_source is None:
            self._save_source = GLib.timeout_add(500, self._save)

    def _save(self):
        self._save_source = None
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, "w") as f:
                json.dump(
                    {
                        "enabled": self._enabled,
                        "temperature": self._temperature,
                        "gamma": self._gamma,
                    },
                    f,
                )
        except Exception as e:
            logger.warning(f"[Hyprsunset] Couldn't save settings: {e}")
        return False


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))
