import os

import config
from widgets.popup_window import PopupWindow

from fabric.widgets.box import Box
from fabric.widgets.image import Image

# TODO: use progressbar or custom cairo widget so that I can update the accent color with css
accent = "#82C480"


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
            anchor="right",
            transition_type="slide-left",
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
