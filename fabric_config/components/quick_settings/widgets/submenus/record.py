from collections.abc import Callable

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label

import fabric_config.config as config
from fabric_config.components.quick_settings.widgets.quick_settings_submenu import (
    QuickSubMenu,
    QuickSubToggle,
)
from fabric_config.services.screen_record import ScreenRecorder

TARGETS = {
    "region": ("Region", "selection-mode-symbolic"),
    "window": ("Window", "focus-windows-symbolic"),
    "screen": ("Screen", "video-display-symbolic"),
}
AUDIO = {
    "none": ("None", "audio-volume-muted-symbolic"),
    "desktop": ("Desktop", "audio-speakers-symbolic"),
    "mic": ("Mic", "audio-input-microphone-symbolic"),
}
TARGET_STATUS = {
    "region": "Select a region",
    "window": "Pick a window",
    "screen": "Focused screen",
}


class SegmentedRow(Box):
    """A row of buttons, one active, bound to a property of the recorder."""

    def __init__(self, options: dict[str, tuple[str, str]], prop: str, **kwargs):
        self.prop = prop
        super().__init__(
            style_classes=["segmented-row"], spacing=4, homogeneous=True, **kwargs
        )
        self.buttons: dict[str, Button] = {}
        for value, (label, icon) in options.items():
            button = self.buttons[value] = Button(
                style_classes=["segmented-button"],
                h_expand=True,
                child=Box(
                    spacing=6,
                    h_align="center",
                    children=[Image(icon_name=icon, icon_size=16), Label(label)],
                ),
                on_clicked=lambda _, v=value: setattr(config.sc, prop, v),
            )
            self.add(button)
        config.sc.connect(f"notify::{prop}", lambda *_: self.sync())
        self.sync()

    def sync(self):
        current = getattr(config.sc, self.prop)
        for value, button in self.buttons.items():
            if value == current:
                button.add_style_class("active")
            else:
                button.remove_style_class("active")


class RecordSubMenu(QuickSubMenu):
    def __init__(self, **kwargs):
        super().__init__(
            title="Screen Recording",
            title_icon="media-record-symbolic",
            child=Box(
                orientation="v",
                spacing=4,
                children=[
                    Label(
                        "Capture",
                        style_classes=["submenu-section-header"],
                        h_align="start",
                    ),
                    SegmentedRow(TARGETS, "target"),
                    Label(
                        "Sound",
                        style_classes=["submenu-section-header"],
                        h_align="start",
                    ),
                    SegmentedRow(AUDIO, "audio"),
                ],
            ),
            **kwargs,
        )


class RecordToggle(QuickSubToggle):
    """Starts a recording with the chosen settings, or stops the running one."""

    def __init__(
        self,
        submenu: RecordSubMenu,
        recorder: ScreenRecorder,
        close_popup: Callable[[], object],
        **kwargs,
    ):
        super().__init__(
            action_icon="media-record-symbolic",
            action_label="",
            title="Record",
            submenu=submenu,
            **kwargs,
        )
        self.recorder = recorder
        self._close_popup = close_popup
        self._recording = False
        self.connect("action-clicked", lambda *_: self._on_clicked())
        recorder.connect("recording", lambda _, status: self._on_recording(status))
        recorder.connect("notify::target", lambda *_: self.update())
        recorder.connect("notify::audio", lambda *_: self.update())
        self.update()

    def _on_clicked(self):
        if self._recording:
            self.recorder.screencast_stop()
            return
        # out of the way of the selection (and of the recording)
        self._close_popup()
        self.recorder.screencast_start()

    def _on_recording(self, recording: bool):
        self._recording = recording
        self.update()

    def update(self):
        self.set_active_style(self._recording)
        if self._recording:
            self.title_label.set_label("Recording")
            self.set_action_label("Click to stop")
            self.set_action_icon("media-playback-stop-symbolic")
            return
        self.title_label.set_label("Record")
        target = self.recorder.target
        audio = self.recorder.audio
        # short: a longer status line widens the whole popup
        status = (
            f"{TARGETS[target][0]} · {'mic' if audio == 'mic' else 'sound'}"
            if audio != "none" and target in TARGETS
            else TARGET_STATUS.get(target, "")
        )
        self.set_action_label(status)
        self.set_action_icon("media-record-symbolic")
