from components.bar.widgets.battery_indicator import BatteryIndicator
from components.bar.widgets.date_time import (
    ActiveWindow,
    DateTime,
    WorkspaceButton,
    Workspaces,
)
from components.bar.widgets.prayer_times import PrayerTimesButton
from components.bar.widgets.systray import SystemTrayRevealer
from components.quick_settings.quick_settings import QuickSettingsButton

# from fabric.hyprland.widgets import ActiveWindow
from fabric.utils.string_formatter import FormattedString
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.wayland import Window


class StatusBar(Window):
    def __init__(
        self,
    ):
        self.center_box = CenterBox(name="main-window")
        self.workspaces = Workspaces(
            name="workspaces",
            spacing=2,
            buttons_list=[
                WorkspaceButton(FormattedString("")),
                WorkspaceButton(FormattedString("")),
                WorkspaceButton(FormattedString("")),
                WorkspaceButton(FormattedString("")),
                WorkspaceButton(FormattedString("")),
                WorkspaceButton(FormattedString("")),
                WorkspaceButton(FormattedString("")),
            ],
        )
        self.active_window = ActiveWindow(
            name="panel-button",
            formatter=FormattedString(
                "{test_title(win_initialTitle)}",
                test_title=lambda x, max_length=40: "Desktop"
                if len(x) == 0
                else (x if len(x) <= max_length else x[: max_length - 3] + "..."),
            ),
        )
        # self.active_window.set_tooltip_text("THIS IS A TOOLTIP")
        self.date_time = DateTime()
        self.battery = BatteryIndicator()
        self.quick_settings = QuickSettingsButton()
        self.prayer_times = PrayerTimesButton()
        self.sys_tray = SystemTrayRevealer(icon_size=20, name = "panel-button")
        self.center_box.end_container.add_children(
            [self.sys_tray, self.quick_settings, self.battery, self.date_time]
        )
        self.center_box.start_container.add_children(
            [self.workspaces, self.prayer_times, self.active_window]
        )

        super().__init__(
            layer="top",
            anchor="left top right",
            exclusive=True,
            visible=True,
            children=self.center_box,
        )

        self.show_all()
