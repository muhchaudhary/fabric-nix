"""
Wallpaper state shared by the wallpaper picker and the overview.

Saved in last_selected.json as {"path": <default for all monitors>,
"monitors": {<monitor name>: <path>}}. A per-monitor entry overrides the
default for that monitor. Older files only have "path" and still load.
"""

import json
import mimetypes
import os
from typing import Callable

from gi.repository import GLib

from fabric_config.utils.hyprland_monitor import get_hyprland_monitors
from fabric_config.utils.process import run_command_async

WALLPAPER_DIR = os.path.join(GLib.get_home_dir(), "wallpapers")
LAST_WALLPAPER_FILE = os.path.join(
    GLib.get_user_cache_dir(), "fabric", "wallpaper-picker", "last_selected.json"
)


def _read_state() -> dict:
    try:
        with open(LAST_WALLPAPER_FILE) as f:
            state = json.load(f)
    except (OSError, ValueError):
        return {"path": None, "monitors": {}}
    if not isinstance(state, dict):
        return {"path": None, "monitors": {}}
    state.setdefault("path", None)
    if not isinstance(state.get("monitors"), dict):
        state["monitors"] = {}
    return state


def _write_state(state: dict):
    try:
        os.makedirs(os.path.dirname(LAST_WALLPAPER_FILE), exist_ok=True)
        tmp = LAST_WALLPAPER_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, LAST_WALLPAPER_FILE)
    except OSError:
        pass


def _existing(path: str | None) -> str | None:
    return path if path and os.path.exists(path) else None


def get_last_wallpaper() -> str | None:
    """The wallpaper last set for all monitors, if it still exists."""
    return _existing(_read_state()["path"])


def wallpaper_for_monitor(monitor_name: str) -> str | None:
    """The saved wallpaper for one monitor, falling back to the default."""
    state = _read_state()
    return _existing(state["monitors"].get(monitor_name)) or _existing(state["path"])


def save_wallpaper(path: str, monitor_names: list[str] | None = None):
    """Remember `path` for the given monitors, or for all when None."""
    if monitor_names is None:
        _write_state({"path": path, "monitors": {}})
        return
    state = _read_state()
    for name in monitor_names:
        state["monitors"][name] = path
    _write_state(state)


# kept for callers that only deal with "all monitors"
def save_last_wallpaper(path: str):
    save_wallpaper(path)


def list_monitors() -> list[dict]:
    """Hyprland's monitor list (name, width, height, focused, ...)."""
    try:
        return json.loads(get_hyprland_monitors().send_command("j/monitors").reply)
    except Exception:
        return []


def apply_wallpaper(
    path: str,
    monitor_names: list[str],
    on_done: Callable[[], None] | None = None,
):
    """Show `path` on the given monitors via hyprpaper."""
    remaining = len(monitor_names)
    if remaining == 0:
        if on_done:
            on_done()
        return

    def done(_ok: bool, _out: str, _err: str):
        nonlocal remaining
        remaining -= 1
        if remaining == 0 and on_done:
            on_done()

    for name in monitor_names:
        run_command_async(["hyprctl", "hyprpaper", "wallpaper", f"{name},{path}"], done)


def query_active_wallpapers(callback: Callable[[dict[str, str]], None]):
    """What each monitor is actually showing, from `hyprpaper listactive`."""

    def on_done(ok: bool, out: str, _err: str):
        active: dict[str, str] = {}
        if ok:
            for line in out.splitlines():
                name, sep, path = line.partition(":")
                if sep and path.strip():
                    active[name.strip()] = path.strip()
        callback(active)

    run_command_async(["hyprctl", "hyprpaper", "listactive"], on_done)


def restore_wallpapers():
    """Re-apply the saved wallpaper to each connected monitor (at startup)."""
    for monitor in list_monitors():
        path = wallpaper_for_monitor(monitor["name"])
        if path:
            apply_wallpaper(path, [monitor["name"]])


def list_wallpapers() -> list[str]:
    """Image file names in WALLPAPER_DIR, most recently modified first."""
    entries = []
    try:
        with os.scandir(WALLPAPER_DIR) as it:
            for entry in it:
                file_type = mimetypes.guess_type(entry.name)[0]
                if not (file_type and file_type.startswith("image/")):
                    continue
                try:
                    mtime = entry.stat().st_mtime
                except OSError:
                    continue
                entries.append((mtime, entry.name))
    except OSError:
        return []
    entries.sort(key=lambda e: (-e[0], e[1].lower()))
    return [name for _, name in entries]
