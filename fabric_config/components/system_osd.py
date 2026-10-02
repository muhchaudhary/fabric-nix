from typing import Literal, cast, get_args

import cairo
from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.shapes import Corner
from gi.repository import Gdk, GLib, Gtk

import fabric_config.config as config
from fabric_config.widgets import PopupWindow

OSDMode = Literal["sound", "mic", "brightness", "kbd"]

# size of the flares joining the panel to the screen edge; keep in step
# with $osd-radius in _osd.scss
CORNER_SIZE = 32
ICON_SIZE = 26
HIDE_AFTER_MS = 1500
FILL_ANIMATION_S = 0.15
# streams and backlights report their initial values while the bar starts;
# those aren't changes worth showing
STARTUP_GRACE_MS = 3000
SCROLL_STEP = 5  # percent


class OSDLevel(Gtk.LevelBar):
    """Vertical bar filling bottom to top, easing between values."""

    def __init__(self):
        super().__init__()
        self.set_mode(Gtk.LevelBarMode.CONTINUOUS)
        self.set_min_value(0.0)
        self.set_max_value(1.0)
        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_inverted(True)
        self.set_vexpand(True)
        self.set_halign(Gtk.Align.CENTER)
        self.get_style_context().add_class("osd-level")
        # only the filled/empty classes; no low/high/full colours
        for offset in ("low", "high", "full"):
            self.remove_offset_value(offset)

        self._from = 0.0
        self._to = 0.0
        self._start: float | None = None
        self._tick_id: int | None = None
        self.show()

    def set_progress(self, fraction: float, animate: bool = True):
        self._to = max(0.0, min(1.0, fraction))
        if not animate or not self.get_mapped():
            if self._tick_id is not None:
                self.remove_tick_callback(self._tick_id)
                self._tick_id = None
            self.set_value(self._to)
            return
        # retarget from wherever the bar is now
        self._from = self.get_value()
        self._start = None
        if self._tick_id is None:
            self._tick_id = self.add_tick_callback(self._on_tick)

    def _on_tick(self, _widget: Gtk.Widget, clock: Gdk.FrameClock) -> bool:
        now = clock.get_frame_time() / 1_000_000
        if self._start is None:
            self._start = now
        t = min(1.0, (now - self._start) / FILL_ANIMATION_S)
        eased = 1 - (1 - t) ** 3
        self.set_value(self._from + (self._to - self._from) * eased)
        if t >= 1:
            self._tick_id = None
            return False
        return True


def _quick_settings_open() -> bool:
    # quick settings has its own sliders; an OSD on top of them is noise
    from fabric_config.components.quick_settings.quick_settings import (
        QuickSettingsPopup,
    )

    return QuickSettingsPopup.popup_visible


def _themed_icon(name: str | None, fallback: str) -> str:
    if name:
        symbolic = name if name.endswith("-symbolic") else f"{name}-symbolic"
        if Gtk.IconTheme.get_default().has_icon(symbolic):
            return symbolic
    return fallback


class SystemOSD(PopupWindow):
    def __init__(self, **kwargs):
        self.brightness = config.brightness
        self.mode: OSDMode = "sound"
        self._hide_id: int | None = None
        self._hovered = False
        self._ready = False
        # what was last shown per source, so unrelated notifies don't pop up
        self._last_shown: dict[str, tuple] = {}
        self._speaker = None
        self._speaker_handlers: list[int] = []
        self._microphone = None
        self._microphone_handlers: list[int] = []

        self.level = OSDLevel()
        self.icon = Image(name="osd-icon")
        self.value_label = Label(name="osd-value")

        self.panel = Box(
            name="osd",
            orientation="v",
            spacing=10,
            h_align="end",
            children=[self.level, self.icon, self.value_label],
        )
        self.panel_events = EventBox(
            events=[
                "enter-notify",
                "leave-notify",
                "scroll",
                "smooth-scroll",
                "button-press",
            ],
            child=self.panel,
            on_enter_notify_event=self._on_enter,
            on_leave_notify_event=self._on_leave,
            on_scroll_event=self._on_scroll,
            on_button_press_event=self._on_click,
            on_size_allocate=lambda *_: self._update_input_region(),
        )

        super().__init__(
            layer="overlay",
            enable_inhibitor=False,
            transition_duration=200,
            anchor="center-right",
            transition_type="slide-left",
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
                            size=CORNER_SIZE,
                        ),
                    ),
                    self.panel_events,
                    Box(
                        style_classes=["osd-corner"],
                        children=Corner(
                            h_align="end",
                            orientation="top-right",
                            size=CORNER_SIZE,
                        ),
                    ),
                ],
            ),
            **kwargs,
        )

        config.audio.connect("notify::speaker", self._on_speaker_switched)
        config.audio.connect("notify::microphone", self._on_microphone_switched)
        self._watch_speaker()
        self._watch_microphone()
        self.brightness.connect(
            "notify::screen-brightness", lambda *_: self._auto_show("brightness")
        )
        self.brightness.connect(
            "notify::keyboard-brightness", lambda *_: self._auto_show("kbd")
        )
        GLib.timeout_add(STARTUP_GRACE_MS, self._on_startup_done)

    def _on_startup_done(self):
        self._ready = True
        # record the starting values, so the first real change is detected
        for mode in ("sound", "mic", "brightness", "kbd"):
            self._last_shown[mode] = self._state(mode)
        return False

    # Sources

    def _watch_speaker(self):
        for handler in self._speaker_handlers:
            if self._speaker is not None:
                self._speaker.disconnect(handler)
        self._speaker = config.audio.speaker
        self._speaker_handlers = (
            [
                self._speaker.connect(
                    f"notify::{prop}", lambda *_: self._auto_show("sound")
                )
                for prop in ("volume", "is-muted")
            ]
            if self._speaker is not None
            else []
        )

    def _watch_microphone(self):
        for handler in self._microphone_handlers:
            if self._microphone is not None:
                self._microphone.disconnect(handler)
        self._microphone = config.audio.microphone
        # mute only: apps with automatic gain move the mic volume constantly
        self._microphone_handlers = (
            [
                self._microphone.connect(
                    "notify::is-muted", lambda *_: self._auto_show("mic")
                )
            ]
            if self._microphone is not None
            else []
        )

    def _on_speaker_switched(self, *_):
        self._watch_speaker()
        if self._ready:
            self._last_shown["sound"] = self._state("sound")
            self.show_osd("sound", device_icon=True)

    def _on_microphone_switched(self, *_):
        self._watch_microphone()
        if self._ready:
            self._last_shown["mic"] = self._state("mic")

    def _state(self, mode: OSDMode) -> tuple:
        match mode:
            case "sound":
                s = config.audio.speaker
                return (round(s.volume), s.muted) if s else ()
            case "mic":
                m = config.audio.microphone
                return (m.muted,) if m else ()
            case "brightness":
                return (self.brightness.screen_brightness,)
            case "kbd":
                return (self.brightness.keyboard_brightness,)

    def _available(self, mode: OSDMode) -> bool:
        match mode:
            case "sound":
                return config.audio.speaker is not None
            case "mic":
                return config.audio.microphone is not None
            case "brightness":
                return self.brightness.max_screen > 0
            case "kbd":
                return self.brightness.max_kbd > 0

    def _auto_show(self, mode: OSDMode):
        if not self._ready:
            return
        state = self._state(mode)
        if self._last_shown.get(mode) == state:
            return
        self._last_shown[mode] = state
        self.show_osd(mode)

    # Display

    def _render(self, mode: OSDMode, device_icon: bool = False):
        muted = False
        match mode:
            case "sound":
                speaker = config.audio.speaker
                muted = bool(speaker and speaker.muted)
                volume_icon = config.audio_icon_name(speaker)
                icon = (
                    _themed_icon(speaker.icon_name, volume_icon)
                    if device_icon and speaker and not muted
                    else volume_icon
                )
                fraction = speaker.volume / 100 if speaker else 0
                text = "Muted" if muted else f"{round(fraction * 100)}"
            case "mic":
                mic = config.audio.microphone
                muted = bool(mic and mic.muted)
                icon = (
                    "microphone-sensitivity-muted-symbolic"
                    if muted
                    else "audio-input-microphone-symbolic"
                )
                fraction = mic.volume / 100 if mic else 0
                text = "Muted" if muted else "Live"
            case "brightness":
                icon = "display-brightness-symbolic"
                fraction = (
                    self.brightness.screen_brightness / self.brightness.max_screen
                )
                text = f"{round(fraction * 100)}"
            case "kbd":
                icon = "keyboard-brightness-symbolic"
                fraction = self.brightness.keyboard_brightness / self.brightness.max_kbd
                text = f"{round(fraction * 100)}"

        animate = self.popup_visible and self.mode == mode
        self.mode = mode
        self.icon.set_from_icon_name(icon, Gtk.IconSize.DIALOG)
        self.icon.set_pixel_size(ICON_SIZE)
        self.value_label.set_label(text)
        self.level.set_progress(fraction, animate=animate)
        if muted:
            self.panel.add_style_class("muted")
        else:
            self.panel.remove_style_class("muted")

    def show_osd(self, mode: OSDMode, device_icon: bool = False):
        if not self._available(mode) or _quick_settings_open():
            return
        self._render(mode, device_icon)

        if not self.popup_visible:
            self.monitor = self.hyprland_monitor.get_current_gdk_monitor_id()
            self.reveal_child.revealer.show()
            self.popup_visible = True
            self.reveal_child.revealer.set_reveal_child(True)
        self._update_input_region()
        self._restart_hide_timer()

    def hide_osd(self):
        self._cancel_hide_timer()
        self.popup_visible = False
        self.reveal_child.revealer.set_reveal_child(False)

    def _restart_hide_timer(self):
        self._cancel_hide_timer()
        if not self._hovered:
            self._hide_id = GLib.timeout_add(HIDE_AFTER_MS, self._on_hide_timeout)

    def _cancel_hide_timer(self):
        if self._hide_id is not None:
            GLib.source_remove(self._hide_id)
            self._hide_id = None

    def _on_hide_timeout(self):
        self._hide_id = None
        self.hide_osd()
        return False

    def _update_input_region(self):
        # only the panel takes input (hover/scroll/click); the rest of the
        # screen-sized window passes clicks through
        alloc = self.panel_events.get_allocation()
        coords = self.panel_events.translate_coordinates(self, 0, 0)
        if not self.popup_visible or coords is None or alloc.width <= 1:
            self.input_shape_combine_region(cairo.Region(cairo.RectangleInt()))
            return
        x, y = coords
        self.input_shape_combine_region(
            cairo.Region(cairo.RectangleInt(x, y, alloc.width, alloc.height))
        )

    # Interaction

    def _on_enter(self, *_):
        self._hovered = True
        self._cancel_hide_timer()

    def _on_leave(self, _widget, event: Gdk.EventCrossing):
        # moving onto a child widget isn't leaving the panel
        if event.detail == Gdk.NotifyType.INFERIOR:
            return
        self._hovered = False
        if self.popup_visible:
            self._restart_hide_timer()

    def _on_scroll(self, _widget, event: Gdk.EventScroll):
        match event.direction:
            case Gdk.ScrollDirection.UP:
                step = 1
            case Gdk.ScrollDirection.DOWN:
                step = -1
            case Gdk.ScrollDirection.SMOOTH:
                step = -1 if event.delta_y > 0 else 1 if event.delta_y < 0 else 0
            case _:
                step = 0
        if step:
            self._adjust(step)
        return True

    def _adjust(self, step: int):
        match self.mode:
            case "sound" | "mic":
                stream = (
                    config.audio.speaker
                    if self.mode == "sound"
                    else config.audio.microphone
                )
                if stream is not None:
                    stream.volume = max(0, min(100, stream.volume + step * SCROLL_STEP))
            case "brightness":
                b = self.brightness
                delta = max(1, round(b.max_screen * SCROLL_STEP / 100))
                b.screen_brightness = max(
                    0, min(b.max_screen, b.screen_brightness + step * delta)
                )
            case "kbd":
                b = self.brightness
                b.keyboard_brightness = max(
                    0, min(b.max_kbd, b.keyboard_brightness + step)
                )

    def _on_click(self, _widget, event: Gdk.EventButton):
        if event.button != 1:
            return False
        stream = {
            "sound": config.audio.speaker,
            "mic": config.audio.microphone,
        }.get(self.mode)
        if stream is not None:
            stream.muted = not stream.muted
        return True

    # DBus action (key binds)

    def enable_popup(self, osd_type: str):
        if osd_type in get_args(OSDMode):
            self.show_osd(cast(OSDMode, osd_type))
