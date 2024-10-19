import os
from typing import Literal

import config
from gi.repository import GLib


from fabric.widgets.widget import Widget
from fabric.widgets.image import Image
from fabric.widgets.box import Box
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow
from gi.repository import GLib
from utils.hyprland_monitor import HyprlandWithMonitors

# TODO: use progressbar or custom cairo widget so that I can update the accent color with css
accent = "#82C480"


# This is only for OSD, I don' want or need an inhibitor for this
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
        keyboard_mode: Literal["none", "exclusive", "on-demand"] = "on-demand",
        timeout: int = 1000,
        decorations: str = "margin: 1px",
        **kwargs,
    ):
        self.timeout = timeout
        self.currtimeout = 0
        self.popup_running = False

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
            child=Box(style=decorations, children=self.revealer),
            keyboard_mode=keyboard_mode,
            **kwargs,
        )
        self.set_can_focus = False

        self.revealer.connect(
            "notify::child-revealed",
            lambda revealer, is_reveal: revealer.hide()
            if not revealer.get_child_revealed()
            else None,
        )

        self.show()

    def toggle_popup(self, monitor: bool = False):
        if monitor:
            curr_monitor = self.hyprland_monitor.get_current_gdk_monitor_id()
            self.monitor = curr_monitor

            if self.monitor_number != curr_monitor and self.visible:
                self.monitor_number = curr_monitor
                return

            self.monitor_number = curr_monitor
        if not self.visible:
            self.revealer.show()
        self.visible = not self.visible
        self.revealer.set_reveal_child(self.visible)

    def toggle_popup_offset(self, offset, toggle_width):
        if not self.visible:
            self.revealer.show()
        self.visible = not self.visible
        self.revealer.set_reveal_child(self.visible)
        self.revealer.set_margin_start(
            offset - (self.revealer.get_allocated_width() - toggle_width) / 2
        )

    def popup_timeout(self):
        curr_monitor = self.hyprland_monitor.get_current_gdk_monitor_id()
        self.monitor = curr_monitor

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


class SystemOSD(PopupWindow):
    def __init__(self, **kwargs):
        self.disp_backlight_path = "/sys/class/backlight/intel_backlight/"
        self.kbd_backlight_path = "/sys/class/leds/tpacpi::kbd_backlight/"
        self.max_disp_backlight = config.brightness.max_screen
        self.max_kbd_backlight = config.brightness.max_kbd
        self.brightness = config.brightness
        self.disp_backlight = 0
        self.kbd_backlight = 0
        self.vol = 0

        self.overlay_fill_box = Box(name="osd-box")
        self.icon = Image()

        super().__init__(
            transition_duration=150,
            anchor="center-right",
            transition_type="slide-up",
            keyboard_mode="none",
            child=Box(
                name="quicksettings",
                orientation="v",
                children=[self.overlay_fill_box, self.icon],
            ),
            **kwargs,
        )

    def update_label_audio(self, *args):
        icon_name = "-".join(str(config.audio.speaker.icon_name).split("-")[0:2])
        self.icon.set_from_icon_name(icon_name + "-symbolic", 6)
        self.vol = config.audio.speaker.volume
        quick_accent = accent
        if config.audio.speaker.muted:
            quick_accent = "#a89984"
        self.overlay_fill_box.set_style(
            f"background-image: linear-gradient(to top, alpha({quick_accent}, 0.8) {round(self.vol)}%, alpha(#303030, 0.8) {round(self.vol)}%);",
        )

    def update_label_brightness(self):
        brightness = self.brightness.screen_brightness / self.max_disp_backlight * 100

        self.icon.set_from_icon_name("display-brightness-symbolic", 6)
        self.overlay_fill_box.set_style(
            f"background-image: linear-gradient(to top, alpha({accent}, 0.8) {brightness}%, alpha(#303030, 0.8) {brightness}%);",
        )

    def update_label_keyboard(self, *args):
        brightness = (
            int(
                os.read(
                    os.open(self.kbd_backlight_path + "brightness", os.O_RDONLY), 6
                ),
            )
            / self.max_kbd_backlight
            * 100
        )

        self.icon.set_from_icon_name("keyboard-brightness-symbolic", 6)
        self.overlay_fill_box.set_style(
            f"background-image: linear-gradient(to top, alpha({accent}, 0.8) {brightness}%, alpha(#303030, 0.8) {brightness}%);",
        )

    def enable_popup(self, type: str):
        if type == "sound":
            self.update_label_audio()
        elif type == "brightness":
            self.update_label_brightness()
        elif type == "kbd":
            self.update_label_keyboard()

        self.popup_timeout()
