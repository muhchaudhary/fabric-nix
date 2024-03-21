"""desktop status bar example"""
import psutil
from loguru import logger
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.wayland import Window
from fabric.widgets.overlay import Overlay
from fabric.widgets.eventbox import EventBox
from fabric.widgets.date_time import DateTime
from fabric.widgets.centerbox import CenterBox
from fabric.utils.string_formatter import FormattedString
from components.bar.widgets.prayer_times import PrayerTimesButton
from fabric.hyprland.widgets import WorkspaceButton, Workspaces, ActiveWindow, Language
from components.bar.widgets.battery_indicator import BatteryIndicator
from components.quick_settings.quick_settings import QuickSettingsButton
from fabric.utils import (
    bulk_replace,
    invoke_repeater,
)

AUDIO_WIDGET = True

if AUDIO_WIDGET is True:
    try:
        from fabric.audio.service import Audio
    except Exception as e:
        logger.error(e)
        AUDIO_WIDGET = False


class StatusBar(Window):
    def __init__(
        self,
    ):
        super().__init__(
            layer="top",
            anchor="left top right",
            # margin="10px 10px -2px 10px",
            exclusive=True,
            visible=True,
        )
        self.center_box = CenterBox(name="main-window")
        self.workspaces = Workspaces(
            name="workspaces",
            spacing=2,
            buttons_list=[
                WorkspaceButton(label=FormattedString("")),
                WorkspaceButton(label=FormattedString("")),
                WorkspaceButton(label=FormattedString("")),
                WorkspaceButton(label=FormattedString("")),
                WorkspaceButton(label=FormattedString("")),
                WorkspaceButton(label=FormattedString("")),
                WorkspaceButton(label=FormattedString("")),
            ],
        )
        self.date_time = DateTime(name="date-time")
        self.battery = BatteryIndicator()
        self.quick_settings = QuickSettingsButton()
        self.prayer_times = PrayerTimesButton()

        # self.widgets_container = Box(
        #     spacing=2,
        #     orientation="h",
        #     name="widgets-container",
        # )
        # self.widgets_container.add(self.volume) if self.volume is not None else None
        # self.center_box.add_right(self.widgets_container)
        self.center_box.add_right(self.quick_settings)
        self.center_box.add_right(self.battery)
        self.center_box.add_left(self.workspaces)
        self.center_box.add_left(self.prayer_times)
        self.center_box.add_center(self.date_time)
        self.add(self.center_box)

        self.show_all()
