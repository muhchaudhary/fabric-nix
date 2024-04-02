from fabric.widgets.wayland import Window
from fabric.widgets.revealer import Revealer
from fabric.widgets.box import Box
from typing import Literal
from fabric.widgets.eventbox import EventBox
from gi.repository import GLib


class inhibitOverlay(Window):
    def __init__(self, size: int = 1920):
        self.eventbox = EventBox(
            events=["button-press", "key-press"],
            style="background-color: alpha(white, 0.005);",
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
        )
        self.eventbox.set_can_focus(True)
        self.connect("key-press-event", lambda *args: print(args))


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
        *kwargs,
    ):
        self.timeout = 1000
        self.eventID = -1
        self.currtimeout = 0
        self.popup_running = False
        self.enable_inhibitor = enable_inhibitor

        self.revealer = Revealer(
            transition_type=transition_type,
            transition_duration=transition_duration,
            children=child,
        )
        self.box = Box(style="padding:1px;", children=self.revealer)
        self.visible = visible
        super().__init__(
            layer="overlay",
            anchor=anchor,
            all_visible=False,
            visible=False,
            exclusive=False,
            children=self.box,
            *kwargs,
        )
        if enable_inhibitor:
            self.inhibitor = inhibitOverlay()
            self.inhibitor.connect("button-press-event", self.on_inhibit_click)
        self.show_all()

    def on_inhibit_click(self, *_):
        self.toggle_popup()

    def toggle_popup(self):
        self.visible = not self.visible
        self.revealer.set_reveal_child(self.visible)
        if self.enable_inhibitor:
            self.inhibitor.set_visible(self.visible)
        return False

    def popup_timeout(self):
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
