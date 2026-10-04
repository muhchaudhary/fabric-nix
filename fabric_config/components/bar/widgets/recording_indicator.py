from time import monotonic

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from gi.repository import GLib

import fabric_config.config as config


def format_elapsed(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes:02}:{secs:02}"


class RecordingIndicator(Button):
    """Shown while recording: a red dot and the elapsed time; click to stop."""

    def __init__(self, **kwargs):
        self.elapsed = Label("00:00", name="recording-elapsed")
        super().__init__(
            name="recording-indicator",
            style_classes=["button-basic", "button-basic-props", "button-border"],
            tooltip_text="Stop recording",
            child=Box(
                spacing=6,
                children=[
                    Image(icon_name="media-record-symbolic", icon_size=16),
                    self.elapsed,
                ],
            ),
            visible=False,
            on_clicked=lambda *_: config.sc.screencast_stop(),
            **kwargs,
        )
        self._tick_source: int | None = None
        config.sc.connect("recording", lambda _, status: self._on_recording(status))

    def _on_recording(self, recording: bool):
        self.set_visible(recording)
        if self._tick_source is not None:
            GLib.source_remove(self._tick_source)
            self._tick_source = None
        if recording:
            self._tick()
            self._tick_source = GLib.timeout_add(1000, self._tick)

    def _tick(self) -> bool:
        since = config.sc.recording_since
        self.elapsed.set_label(format_elapsed(monotonic() - since if since else 0))
        return True
