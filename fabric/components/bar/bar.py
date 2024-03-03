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
from fabric.widgets.circular_progress_bar import CircularProgressBar
from fabric.hyprland.widgets import WorkspaceButton, Workspaces, ActiveWindow, Language
from services.mpris import MprisPlayerManager
from widgets.player import PlayerBoxHandler
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

class VolumeWidget(Box):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.audio = Audio()

        self.circular_progress_bar = CircularProgressBar(
            name="volume-circular-progress-bar",
            background_color=False,  # false = disabled
            radius_color=False,
            pie=True,
        )

        self.event_box = EventBox(
            events="scroll",
            children=Overlay(
                children=self.circular_progress_bar,
                overlays=Label(
                    label="",
                    style="margin: 0px 6px 0px 0px; font-size: 12px",  # because glyph icon is not centered
                ),
            ),
        )

        self.event_box.connect("scroll-event", self.on_scroll)
        self.audio.connect("speaker-changed", self.update)
        self.add(self.event_box)

    def on_scroll(self, widget, event):
        if event.direction == 0:
            self.audio.speaker.volume += 8
        elif event.direction == 1:
            self.audio.speaker.volume -= 8

    def update(self, *args):
        if self.audio.speaker is None:
            return
        self.circular_progress_bar.percentage = self.audio.speaker.volume
        return

class StatusBar(Window):
    def __init__(
        self,
    ):
        super().__init__(
            layer="top",
            anchor="left top right",
            margin="10px 10px -2px 10px",
            exclusive=True,
            visible=True,
        )
        self.center_box = CenterBox(name="main-window")
        self.workspaces = Workspaces(
            spacing=2,
            name="workspaces",
            buttons_list=[
                WorkspaceButton(label=FormattedString("1")),
                WorkspaceButton(label=FormattedString("2")),
                WorkspaceButton(label=FormattedString("3")),
                WorkspaceButton(label=FormattedString("4")),
                WorkspaceButton(label=FormattedString("5")),
                WorkspaceButton(label=FormattedString("6")),
                WorkspaceButton(label=FormattedString("7")),
            ],
        )
        self.active_window = ActiveWindow(
            formatter=FormattedString(
                "{test_title(win_class)}",
                test_title=lambda x, max_length=20: "Desktop"
                if len(x) == 0
                else x
                if len(x) <= max_length
                else x[: max_length - 3] + "...",
            ),
            name="hyprland-window",
        )
        self.language = Language(
            formatter=FormattedString(
                "{replace_lang(language)}",
                replace_lang=lambda x: bulk_replace(
                    x,
                    [r".*Eng.*", r".*Ar.*"],
                    ["ENG", "ARA"],
                    regex=True,
                ),
            ),
            name="hyprland-window",
        )
        self.date_time = DateTime(name="date-time")
        self.ram_circular_progress_bar = CircularProgressBar(
            name="ram-circular-progress-bar",
            background_color=False,  # false = disabled
            radius_color=False,
            pie=True,
        )
        self.cpu_circular_progress_bar = CircularProgressBar(
            name="cpu-circular-progress-bar",
            background_color=False,
            radius_color=False,
            pie=True,
        )
        self.circular_progress_bars_overlay = Overlay(
            children=self.ram_circular_progress_bar,
            overlays=[
                self.cpu_circular_progress_bar,
                Label("", style="margin: 0px 6px 0px 0px; font-size: 12px"),
            ],
        )
        self.volume = VolumeWidget() if AUDIO_WIDGET is True else None


        # self.mprisplayer = MprisPlayerManager()
        # self.mprisBox = PlayerBoxHandler(mpris_manager = self.mprisplayer)
        
        self.widgets_container = Box(
            spacing=2,
            orientation="h",
            name="widgets-container",
            children=[
                self.circular_progress_bars_overlay,
            ],
        )
        self.widgets_container.add(self.volume) if self.volume is not None else None
        self.center_box.add_left(self.workspaces)
        self.center_box.add_right(self.widgets_container)
        self.center_box.add_right(self.date_time)
        self.center_box.add_right(self.language)
        # self.center_box.add_center(self.mprisBox)
        self.add(self.center_box)
        invoke_repeater(1000, self.update_progress_bars)
        self.update_progress_bars()  # initial call

        self.show_all()
    
    def update_progress_bars(self):
        self.ram_circular_progress_bar.percentage = psutil.virtual_memory().percent
        self.cpu_circular_progress_bar.percentage = psutil.cpu_percent()
        return True

