import json
from typing import Dict

import gi

import warnings

from fabric.hyprland import Hyprland

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk

# IDC,  screen.get_monitor_plug_name is deprecated
warnings.filterwarnings("ignore", category=DeprecationWarning)


class HyprlandWithMonitors(Hyprland):
    def __init__(self, commands_only: bool = False, **kwargs):
        self.display: Gdk.Display = Gdk.Display.get_default()
        self.screen: Gdk.Screen = Gdk.Display.get_default().get_default_screen()
        super().__init__(commands_only, **kwargs)

    # Add new arguments
    def get_all_monitors(self) -> Dict:
        monitors = json.loads(self.send_command("j/monitors").reply)
        return {monitor["id"]: monitor["name"] for monitor in monitors}

    def get_gdk_monitor_id_from_name(self, plug_name: str) -> int | None:
        for i in range(self.display.get_n_monitors()):
            if self.screen.get_monitor_plug_name(i) == plug_name:
                return i
        return None

    def get_gdk_monitor_id(self, hyprland_id: int) -> int | None:
        monitors = self.get_all_monitors()
        if hyprland_id in monitors:
            return self.get_gdk_monitor_id_from_name(monitors[hyprland_id])
        return None

    def get_current_gdk_monitor_id(self) -> int | None:
        active_workspace = json.loads(self.send_command("j/activeworkspace").reply)
        return self.get_gdk_monitor_id_from_name(active_workspace["monitor"])
