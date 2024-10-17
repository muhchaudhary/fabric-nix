# from fabric.widgets.wayland import Window
from typing import Literal

from fabric.widgets.widget import Widget
from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow
from gi.repository import GLib
from utils.hyprland_monitor import HyprlandWithMonitors


class inhibitOverlay(WaylandWindow):
    def __init__(self, size: int = 1920):
        self.eventbox = EventBox(
            events=["button-press", "key-release"],
            # style="background-color: alpha(white, 0.005);",
            size=(size),
        )
        super().__init__(
            layer="top",
            anchor="center top",
            type="popup",
            all_visible=False,
            visible=False,
            exclusive=False,
            child=self.eventbox,
            keyboard_mode="on-demand",
        )


class PopupWindow(WaylandWindow):
    def __init__(
        self,
        child: Widget | None = None,
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
        keyboard_mode: Literal["none", "exclusive", "on-demand"] = "on-demand",
        timeout: int = 1000,
        **kwargs,
    ):
        self.timeout = timeout
        self.eventID = -1
        self.currtimeout = 0
        self.popup_running = False
        self.enable_inhibitor = enable_inhibitor
        self.monitor_number: int | None = None
        self.hyprland_monitor = HyprlandWithMonitors()
        self.revealer = Revealer(
            child=child,
            transition_type=transition_type,
            transition_duration=transition_duration,
            visible=False,
        )
        self.visible = visible
        super().__init__(
            layer="overlay",
            anchor=anchor,
            all_visible=False,
            visible=False,
            exclusive=False,
            child=Box(style="margin: 1px;", children=self.revealer),
            keyboard_mode=keyboard_mode,
            **kwargs,
        )

        self.revealer.connect(
            "notify::child-revealed",
            lambda revealer, is_reveal: revealer.hide()
            if not revealer.get_child_revealed()
            else None,
        )

        if enable_inhibitor:
            self.inhibitor = inhibitOverlay()
            self.inhibitor.connect("button-press-event", self.on_inhibit_click)
            self.inhibitor.connect("key-release-event", self.on_key_release)
        self.show()

    def on_key_release(self, _, event_key):
        if event_key.get_keycode()[1] == 9:
            self.visible = False
            self.revealer.set_reveal_child(self.visible)
            self.inhibitor.set_visible(self.visible)

    def on_inhibit_click(self, *_):
        self.visible = False
        self.revealer.set_reveal_child(self.visible)
        if self.enable_inhibitor:
            self.inhibitor.set_visible(self.visible)

    def toggle_popup(self, monitor: bool = False):
        if monitor:
            curr_monitor = self.hyprland_monitor.get_current_gdk_monitor_id()
            self.monitor = curr_monitor
            if self.enable_inhibitor:
                self.inhibitor.monitor = curr_monitor

            if self.monitor_number != curr_monitor and self.visible:
                self.monitor_number = curr_monitor
                return

            self.monitor_number = curr_monitor
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
