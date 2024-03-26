from fabric.widgets.wayland import Window
from fabric.widgets.revealer import Revealer
from fabric.widgets.label import Label
from fabric.widgets.box import Box

from gi.repository import GLib


class PopupWindow(Window):
    def __init__(
        self,
        child = None,
        transition_type: str = "",
        transition_duration: int = 100,
        visible: bool = False,
        anchor: str = "top right",
        *kwargs,
    ):

        self.timeout = 1000
        self.currtimeout = 0
        self.popup_running = False

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
            all_visible=True,
            exclusive=False,
            children=self.box,
            *kwargs
        )

        self.show_all()

    def toggle_popup(self):
        self.visible = not self.visible
        self.revealer.set_reveal_child(self.visible)

    def popup_timeout(self):
        if self.popup_running:
            self.currtimeout = 0
            return
        self.visible = True
        self.revealer.set_reveal_child(True)
        def popup_func():
            if self.currtimeout > self.timeout:
                self.visible = False
                self.revealer.set_reveal_child(False)
                self.currtimeout = 0
                self.popup_running = False
                return False
            self.popup_running = True
            self.currtimeout += 50
            return True
        GLib.timeout_add(100, popup_func)

    def popup_rest(self):
        self.currtimeout = 0
