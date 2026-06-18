from typing import Callable, Iterable, Literal, override

from fabric.hyprland.widgets import HyprlandWorkspaces, WorkspaceButton
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.datetime import DateTime
from fabric.widgets.image import Image
from fabric.widgets.shapes import Corner
from fabric.widgets.wayland import WaylandWindow

from fabric_config import config
from fabric_config.components.bar.widgets import (
    BatteryIndicator,
    PrayerTimesButton,
    SystemTemps,
    SystemTrayRevealer,
)
from fabric_config.components.bar.widgets.clipboard_history import (
    ClipboardHistoryButton,
)
from fabric_config.components.bar.widgets.power_menu import PowerMenuButton
from fabric_config.components.bar.widgets.wallpaper_picker import WallpapperPickerButton
from fabric_config.components.quick_settings.quick_settings import QuickSettingsButton


class HyprlandWorkspaceFix(HyprlandWorkspaces):
    def __init__(
        self,
        buttons: Iterable[WorkspaceButton] | None = None,
        buttons_factory: Callable[[int], WorkspaceButton | None]
        | None = HyprlandWorkspaces.default_buttons_factory,
        invert_scroll: bool = False,
        empty_scroll: bool = False,
        **kwargs,
    ):
        super().__init__(
            buttons, buttons_factory, invert_scroll, empty_scroll, **kwargs
        )

    # override signals again to use lua syntax
    @override
    def do_action_next(self):
        target = "e+1" if not self._empty_scroll else "+1"
        return self.connection.send_command(
            f"/dispatch hl.dsp.focus({{ workspace = '{target}' }})"
        )

    @override
    def do_action_previous(self):
        target = "e-1" if not self._empty_scroll else "-1"

        return self.connection.send_command(
            f"/dispatch hl.dsp.focus({{ workspace = '{target}' }})"
        )

    @override
    def do_button_clicked(self, button: WorkspaceButton):
        return self.connection.send_command(
            f"/dispatch hl.dsp.focus({{ workspace = {button.id} }})"
        )


class StatusBarCorner(Box):
    def __init__(self, corner: Literal["top-right", "top-left"]):
        super().__init__(
            # style="margin-bottom: 25px;",
            orientation="vertical",
            h_expand=False,
            v_expand=False,
            name="system-bar-corner",
            children=[
                Corner(
                    orientation=corner,
                    size=10,
                ),
                Box(
                    v_expand=True,
                    style="background-color: unset;",
                ),
            ],
        )


class StatusBarSeperated(WaylandWindow):
    def __init__(self):
        self.bar_content = CenterBox(name="system-bar")

        self.workspaces = HyprlandWorkspaceFix(
            name="workspaces",
            spacing=2,
            buttons=[
                WorkspaceButton(
                    i,
                    style_classes=[
                        "button-basic",
                        "button-basic-props",
                        "button-border",
                    ],
                )
                for i in range(1, 7)
            ],
            buttons_factory=None,
        )

        self.recording_indicator = Button(
            style_classes=["button-basic", "button-basic-props", "button-border"],
            child=Image(icon_name="media-record-symbolic"),
            visible=False,
            on_clicked=lambda *_: config.sc.screencast_stop(),
        )

        config.sc.connect(
            "recording",
            lambda _, status: self.recording_indicator.set_visible(status),
        )

        # self.open_apps_bar = OpenAppsBar()
        self.date_time = DateTime(
            formatters="%a %b %d  %I:%M %p",
            style_classes=["button-basic", "button-basic-props", "button-border"],
        )
        self.battery = BatteryIndicator()
        self.quick_settings = QuickSettingsButton()
        self.prayer_times = PrayerTimesButton()
        self.wallpaper_button = WallpapperPickerButton()
        self.clipboard_button = ClipboardHistoryButton()
        self.system_temps = SystemTemps()
        self.system_tray = SystemTrayRevealer(icon_size=25)

        self.power_menu = PowerMenuButton()

        self.bar_content.end_children = [
            StatusBarCorner("top-right"),
            Box(
                name="system-bar-group",
                children=[
                    self.recording_indicator,
                    self.system_temps,
                    self.system_tray,
                    self.quick_settings,
                    self.battery,
                    self.date_time,
                    self.power_menu,
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
                    self.wallpaper_button,
                    self.clipboard_button,
                ],
                style_classes="left",
            ),
            StatusBarCorner("top-left"),
        ]
        self.bar_content.center_children = [
            StatusBarCorner("top-right"),
            CenterBox(
                name="system-bar-group",
                center_children=[
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

        # self.show_all()


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
                orientation=orientation,
                size=20,
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
