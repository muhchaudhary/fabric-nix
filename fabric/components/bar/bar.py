# from fabric.hyprland.widgets import ActiveWindow
from components.bar.widgets import (
    BatteryIndicator,
    PrayerTimesButton,
    SystemTrayRevealer,
    Temps,
)
from components.bar.widgets.date_time import DateTime
from components.quick_settings.quick_settings import QuickSettingsButton

from fabric.hyprland.widgets import WorkspaceButton, Workspaces, ActiveWindow

from fabric.utils.string_formatter import FormattedString
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.wayland import Window


class WorkspaceButtonNoLabel(WorkspaceButton):
    def __init__(self):
        super().__init__()

    def bake_label(self):
        return None


class StatusBar(Window):
    def __init__(
        self,
    ):
        self.center_box = CenterBox(name="main-window")
        self.workspaces = Workspaces(
            name="workspaces",
            spacing=2,
            buttons_list=[
                WorkspaceButtonNoLabel(),
                WorkspaceButtonNoLabel(),
                WorkspaceButtonNoLabel(),
                WorkspaceButtonNoLabel(),
                WorkspaceButtonNoLabel(),
                WorkspaceButtonNoLabel(),
                WorkspaceButtonNoLabel(),
            ],
        )
        self.active_window = ActiveWindow(
            name="panel-button",
            formatter=FormattedString(
                "{test_title(win_class)}",
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
        self.sys_tray = SystemTrayRevealer(icon_size=25, name="system-tray")
        self.center_box.end_container.add_children(
            [
                self.sysinfo,
                self.sys_tray,
                self.quick_settings,
                self.battery,
                self.date_time,
            ],
        )
        self.center_box.start_container.add_children(
            [
                self.workspaces,
                self.prayer_times,
                self.active_window,
            ],
        )

        super().__init__(
            layer="top",
            anchor="left top right",
            exclusive=True,
            visible=True,
            children=self.center_box,
        )

        self.show_all()
