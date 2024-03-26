from components.bar.widgets.prayer_times import PrayerTimesButton
from components.bar.widgets.date_time import DateTime, WorkspaceButton, Workspaces
from fabric.widgets.wayland import Window
from fabric.widgets.centerbox import CenterBox
from fabric.hyprland.widgets import ActiveWindow
from fabric.utils.string_formatter import FormattedString
from components.bar.widgets.battery_indicator import BatteryIndicator
from components.quick_settings.quick_settings import QuickSettingsButton


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
                "{win_class}",
            ),
        )
        self.date_time = DateTime()
        self.battery = BatteryIndicator()
        self.quick_settings = QuickSettingsButton()
        self.prayer_times = PrayerTimesButton()

        self.center_box.right_widgets.add_children(
            [self.quick_settings, self.battery, self.date_time]
        )
        self.center_box.left_widgets.add_children(
            [self.workspaces, self.prayer_times, self.active_window]
        )

        super().__init__(
            layer="top",
            anchor="left top right",
            open_inspector=True,
            exclusive=True,
            visible=True,
            children=self.center_box
        )

        self.show_all()
