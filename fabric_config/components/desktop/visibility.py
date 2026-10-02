"""
Whether each monitor's desktop is showing: no windows on its active
workspace and no special workspace open over it.

Animated desktop layers pause while their monitor's desktop is covered, and
the greeting shows when you come back to it. One Hyprland event connection
for the whole desktop (each non-commands-only connection opens its own
event-socket listener).
"""

import json

from fabric.core.service import Service, Signal
from fabric.hyprland import Hyprland
from gi.repository import GLib
from loguru import logger

_EVENTS = (
    "workspace",
    "workspacev2",
    "focusedmon",
    "activespecial",
    "openwindow",
    "closewindow",
    "movewindow",
    "movewindowv2",
    "monitoradded",
    "monitorremoved",
)


class DesktopVisibility(Service):
    @Signal
    def changed(self) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._visible: dict[str, bool] = {}
        self._timer: int | None = None
        self._connection = Hyprland()
        for event in _EVENTS:
            self._connection.connect(f"event::{event}", lambda *_: self._update_soon())
        self._update_soon()

    def visible(self, monitor_name: str) -> bool:
        return self._visible.get(monitor_name, True)

    def any_visible(self) -> bool:
        return any(self._visible.values()) if self._visible else True

    def _update_soon(self):
        # a workspace switch fires several events at once; settle first
        if self._timer is None:
            self._timer = GLib.timeout_add(60, self._update)

    def _update(self):
        self._timer = None
        try:
            monitors = json.loads(self._connection.send_command("j/monitors").reply)
            workspaces = json.loads(self._connection.send_command("j/workspaces").reply)
        except Exception as e:
            logger.warning(f"[Desktop] Couldn't read workspaces: {e}")
            return False
        windows = {ws["id"]: ws.get("windows", 0) for ws in workspaces}
        visible = {}
        for monitor in monitors:
            active = monitor.get("activeWorkspace", {}).get("id")
            special = monitor.get("specialWorkspace", {}).get("id", 0)
            visible[monitor["name"]] = windows.get(active, 0) == 0 and not special
        if visible != self._visible:
            self._visible = visible
            self.changed()
        return False
