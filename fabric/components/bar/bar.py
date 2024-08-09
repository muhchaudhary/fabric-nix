from components.bar.widgets import (
    BatteryIndicator,
    PrayerTimesButton,
    SystemTrayRevealer,
    Temps,
)
from components.bar.widgets.date_time import DateTime
from components.quick_settings.quick_settings import QuickSettingsButton

from fabric.hyprland.widgets import WorkspaceButton, Workspaces, ActiveWindow

from fabric.utils import FormattedString
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.wayland import WaylandWindow


class WorkspaceButtonNoLabel(WorkspaceButton):
    def __init__(self, id):
        super().__init__(id=id)

    def do_bake_label(self):
        return None


class StatusBar(WaylandWindow):
    def __init__(
        self,
    ):
        # causes gtk issue, look into this
        self.center_box = CenterBox(name="main-window")
        self.workspaces = Workspaces(
            name="workspaces",
            spacing=2,
            # buttons_factory=lambda x: WorkspaceButtonNoLabel(x),
            buttons_factory=None,
            buttons=[
                WorkspaceButtonNoLabel(1),
                WorkspaceButtonNoLabel(2),
                WorkspaceButtonNoLabel(3),
                WorkspaceButtonNoLabel(4),
                WorkspaceButtonNoLabel(5),
                WorkspaceButtonNoLabel(6),
                WorkspaceButtonNoLabel(7),
            ],
        )
        self.active_window = ActiveWindow(
            name="panel-button",
            formatter=FormattedString(
                "{test_title(win_title)}",
                test_title=lambda x, max_length=40: "Desktop"
                if len(x) == 0
                else (
                    x.capitalize()
                    if len(x) <= max_length
                    else x[: max_length - 3].capitalize() + "..."
                ),
            ),
        )
        self.date_time = DateTime()
        self.battery = BatteryIndicator()
        self.quick_settings = QuickSettingsButton()
        self.prayer_times = PrayerTimesButton()
        self.sysinfo = Temps()
        # self.sys_tray = SystemTrayRevealer(icon_size=25, name="system-tray")
        self.center_box.end_children = [
            self.sysinfo,
            # self.sys_tray,
            self.quick_settings,
            self.battery,
            self.date_time,
        ]

        self.center_box.start_children = [
            self.workspaces,
            self.prayer_times,
            self.active_window,
        ]

        super().__init__(
            layer="top",
            anchor="left top right",
            exclusivity="auto",
            visible=True,
            child=self.center_box,
        )

        self.show_all()
