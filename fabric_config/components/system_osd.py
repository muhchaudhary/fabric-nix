from fabric.widgets.box import Box
from fabric.widgets.image import Image
from fabric.widgets.shapes import Corner
from fabric_config.widgets import PopupWindow

import fabric_config.config as config

from gi.repository import Gtk


class OSDLevelBar(Gtk.LevelBar):
    """Vertical discrete level bar for the OSD, filling from bottom to top."""

    def __init__(self, ticks: int = 20):
        super().__init__()
        self.set_mode(Gtk.LevelBarMode.DISCRETE)
        self.set_min_value(0.0)
        self.set_max_value(float(ticks))
        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_inverted(True)
        self.set_vexpand(True)
        self.get_style_context().add_class("osd-level-bar")
        # Remove default severity offsets so only filled/empty classes apply.
        for offset in ("low", "high", "full"):
            self.remove_offset_value(offset)
        self._ticks = ticks
        self.show()

    def set_progress(self, percent: float):
        self.set_value(max(0.0, min(1.0, percent)) * self._ticks)


class SystemOSD(PopupWindow):
    def __init__(self, **kwargs):
        self.brightness = config.brightness
        self.level_bar = OSDLevelBar(ticks=20)
        self.icon = Image()

        super().__init__(
            layer="overlay",
            enable_inhibitor=False,
            transition_duration=150,
            anchor="center-right",
            transition_type="crossfade",
            keyboard_mode="none",
            decorations="margin: 1px 0px 1px 1px;",
            child=Box(
                orientation="v",
                h_align="end",
                children=[
                    Box(
                        style_classes=["osd-corner"],
                        children=Corner(
                            h_align="end",
                            orientation="bottom-right",
                            size=50,
                        ),
                    ),
                    Box(
                        name="osd",
                        orientation="v",
                        spacing=10,
                        h_align="end",
                        children=[
                            self.level_bar,
                            Box(name="osd-icon", children=self.icon),
                        ],
                    ),
                    Box(
                        style_classes=["osd-corner"],
                        children=Corner(
                            h_align="end",
                            orientation="top-right",
                            size=50,
                        ),
                    ),
                ],
            ),
            **kwargs,
        )

    def update_label_audio(self, *_):
        speaker = config.audio.speaker
        self.icon.set_from_icon_name(config.audio_icon_name(speaker), 42)
        self.level_bar.set_progress(speaker.volume / 100 if speaker else 0)

    def update_label_brightness(self):
        self.icon.set_from_icon_name("display-brightness-symbolic", 42)
        self.level_bar.set_progress(
            self.brightness.screen_brightness / self.brightness.max_screen
        )

    def update_label_keyboard(self, *_):
        self.icon.set_from_icon_name("keyboard-brightness-symbolic", 42)
        self.level_bar.set_progress(
            self.brightness.keyboard_brightness / self.brightness.max_kbd
        )

    def enable_popup(self, osd_type: str):
        match osd_type:
            case "sound":
                self.update_label_audio()
            case "brightness":
                self.update_label_brightness()
            case "kbd":
                self.update_label_keyboard()

        self.popup_timeout()
