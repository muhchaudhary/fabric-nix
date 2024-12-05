from typing import Literal

from fabric.hyprland.widgets import ActiveWindow, WorkspaceButton, Workspaces
from fabric.utils import FormattedString
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.datetime import DateTime
from fabric.widgets.shapes import Corner
from fabric.widgets.wayland import WaylandWindow

from fabric_config.components.bar.widgets import (
    BatteryIndicator,
    OpenAppsBar,
    PrayerTimesButton,
    SystemTemps,
    SystemTrayRevealer,
)
from fabric_config.components.quick_settings.quick_settings import QuickSettingsButton


class WorkspaceButtonNoLabel(WorkspaceButton):
    def __init__(self, id):
        super().__init__(id=id)

    def do_bake_label(self):
        return None


class StatusBarCorner(Box):
    def __init__(self, corner: Literal["top-right", "top-left"]):
        super().__init__(
            style="margin-bottom: 15px;",
            name="system-bar-corner",
            children=Corner(
                orientation=corner,
                size=15,
            ),
        )


class StatusBarSeperated(WaylandWindow):
    def __init__(self):
        self.bar_content = CenterBox(name="system-bar")

        self.workspaces = Workspaces(
            name="workspaces",
            spacing=2,
            buttons=[WorkspaceButtonNoLabel(i) for i in range(1, 7)],
            buttons_factory=None,
        )

        self.open_apps_bar = OpenAppsBar()
        self.date_time = DateTime(formatters="%a %b %d  %I:%M %p", name="panel-button")
        self.battery = BatteryIndicator()
        self.quick_settings = QuickSettingsButton()
        self.prayer_times = PrayerTimesButton()
        self.system_temps = SystemTemps()
        self.system_tray = SystemTrayRevealer(icon_size=25, name="system-tray")

        self.bar_content.end_children = [
            StatusBarCorner("top-right"),
            Box(
                name="system-bar-group",
                children=[
                    self.system_temps,
                    self.system_tray,
                    self.quick_settings,
                    self.battery,
                    self.date_time,
                ],
                style_classes="right",
            ),
            # StatusBarCorner("top-left"),
        ]

        self.bar_content.start_children = [
            # StatusBarCorner("top-right"),
            Box(
                name="system-bar-group",
                children=[
                    self.prayer_times,
                    self.open_apps_bar,
                ],
                style_classes="left",
            ),
            StatusBarCorner("top-left"),
        ]
        self.bar_content.center_children = [
            StatusBarCorner("top-right"),
            Box(
                name="system-bar-group",
                children=[
                    self.workspaces,
                ],
                style_classes="center",
            ),
            StatusBarCorner("top-left"),
        ]

        super().__init__(
            layer="top",
            anchor="left top right",
            exclusivity="auto",
            visible=True,
            child=self.bar_content,
        )

        self.show_all()


class StatusBar(WaylandWindow):
    def __init__(
        self,
    ):
        # causes gtk issue, look into this
        self.center_box = CenterBox(name="main-window")
        self.workspaces = Workspaces(
            name="workspaces",
            spacing=2,
            buttons=[WorkspaceButtonNoLabel(i + 1) for i in range(7)],
            buttons_factory=None,
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
        self.open_apps_bar = OpenAppsBar()
        self.date_time = DateTime()
        self.battery = BatteryIndicator()
        self.quick_settings = QuickSettingsButton()
        self.prayer_times = PrayerTimesButton()
        self.sysinfo = SystemTemps()
        self.sys_tray = SystemTrayRevealer(icon_size=25, name="system-tray")
        self.center_box.end_children = [
            self.sysinfo,
            self.sys_tray,
            self.quick_settings,
            self.battery,
            self.date_time,
        ]

        self.center_box.start_children = [
            StatusBarCorner("top-right"),
            self.prayer_times,
            self.open_apps_bar,
            StatusBarCorner("top-left"),
            # self.active_window,
        ]
        self.center_box.center_children = [self.workspaces]

        super().__init__(
            layer="top",
            anchor="left top right",
            exclusivity="auto",
            visible=True,
            child=self.center_box,
        )

        self.show_all()


class ScreenCorners(WaylandWindow):
    def __init__(self):
        super().__init__(
            layer="top",
            anchor="top left bottom right",
            pass_through=True,
            child=Box(
                orientation="vertical",
                children=[
                    Box(
                        children=[
                            self.make_corner("top-left"),
                            Box(h_expand=True),
                            self.make_corner("top-right"),
                        ]
                    ),
                    Box(v_expand=True),
                    Box(
                        children=[
                            self.make_corner("bottom-left"),
                            Box(h_expand=True),
                            self.make_corner("bottom-right"),
                        ]
                    ),
                ],
            ),
        )

    def make_corner(self, orientation) -> Box:
        return Box(
            h_expand=False,
            v_expand=False,
            name="system-bar-corner",
            children=Corner(
                orientation=orientation,  # type: ignore
                size=15,
            ),
        )


# Uses up a lot more memory
# class ScreenCorner(WaylandWindow):
#     def __init__(
#         self,
#         orientation: Literal["top left", "top right", "bottom left", "bottom right"],
#     ):
#         print(orientation.replace(" ", "-"))
#         super().__init__(
#             layer="top",
#             anchor=orientation,
#             # pass_through=True,
#             child=Box(
#                 name="system-bar-corner",
#                 children=Corner(
#                     orientation=orientation.replace(" ", "-"),  # type: ignore
#                     size=15,
#                 ),
#             ),
#         )
