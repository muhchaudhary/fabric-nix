# from fabric.widgets.wayland import Window
from typing import Literal

from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import Window
from gi.repository import GLib


class inhibitOverlay(Window):
    def __init__(self, size: int = 1920):
        self.eventbox = EventBox(
            events=["button-press", "key-release"],
            # style="background-color: alpha(white, 0.005);",
            size=(size),
        )
        self.eventbox.set_can_focus(True)
        super().__init__(
            layer="top",
            anchor="center top",
            all_visible=False,
            visible=False,
            exclusive=False,
            children=self.eventbox,
            keyboard_mode="on-demand",
        )
        self.eventbox.set_can_focus(True)


class PopupWindow(Window):
    def __init__(
        self,
        child=None,
        transition_type: Literal[
            "none",
            "crossfade",
            "slide-right",
            "slide-left",
            "slide-up",
            "slide-down",
        ]
        | None = None,
        transition_duration: int = 100,
        visible: bool = False,
        anchor: str = "top right",
        enable_inhibitor: bool = False,
        keyboard_mode: str = "on-demand",
        timeout: int = 1000,
        *kwargs,
    ):
        self.timeout = timeout
        self.eventID = -1
        self.currtimeout = 0
        self.popup_running = False
        self.enable_inhibitor = enable_inhibitor

        self.revealer = Revealer(
            transition_type=transition_type,
            transition_duration=transition_duration,
            children=child,
            visible=False,
        )
        self.revealer_box = Box(style="padding:1px;", children=self.revealer)
        self.visible = visible
        super().__init__(
            layer="overlay",
            anchor=anchor,
            all_visible=False,
            visible=False,
            exclusive=False,
            children=self.revealer_box,
            keyboard_mode=keyboard_mode,
            *kwargs,
        )

        self.revealer.connect(
            "notify::child-revealed",
            lambda revealer, is_reveal: self.revealer.hide()
            if not revealer.get_child_revealed()
            else None,
        )

        if enable_inhibitor:
            self.inhibitor = inhibitOverlay()
            self.inhibitor.connect("button-press-event", self.on_inhibit_click)
            self.inhibitor.connect("key-release-event", self.on_key_release)
        self.show()

    def on_key_release(self, entry, event_key):
        if event_key.get_keycode()[1] == 9:
            self.visible = False
            self.revealer.set_reveal_child(self.visible)
            if self.enable_inhibitor:
                self.inhibitor.set_visible(self.visible)

    def on_inhibit_click(self, *_):
        self.visible = False
        self.revealer.set_reveal_child(self.visible)
        if self.enable_inhibitor:
            self.inhibitor.set_visible(self.visible)

    def toggle_popup(self):
        if not self.visible:
            self.revealer.show()
        self.visible = not self.visible
        self.revealer.set_reveal_child(self.visible)
        if self.enable_inhibitor:
            self.inhibitor.set_visible(self.visible)

    def toggle_popup_offset(self, offset, toggle_width):
        if not self.visible:
            self.revealer.show()
        self.visible = not self.visible
        self.revealer.set_reveal_child(self.visible)
        self.revealer.set_margin_start(
            offset - (self.revealer.get_allocated_width() - toggle_width) / 2
        )
        if self.enable_inhibitor:
            self.inhibitor.set_visible(self.visible)

    def popup_timeout(self):
        if not self.visible:
            self.revealer.show()
        if self.popup_running:
            self.currtimeout = 0
            return
        self.visible = True
        self.revealer.set_reveal_child(self.visible)
        self.popup_running = True

        def popup_func():
            if self.currtimeout >= self.timeout:
                self.visible = False
                self.revealer.set_reveal_child(self.visible)
                self.currtimeout = 0
                self.popup_running = False
                return False
            self.currtimeout += 500
            return True

        GLib.timeout_add(500, popup_func)
