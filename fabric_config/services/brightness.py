import os

from fabric.core.service import Service, Property
from fabric.utils import exec_shell_command_async, monitor_file
from gi.repository import GLib


def exec_brightnessctl_async(args: str):
    exec_shell_command_async(f"brightnessctl {args}", lambda _: None)


SCREEN = os.listdir("/sys/class/backlight")[0]
leds = os.listdir("/sys/class/leds")

kbd = ""
if "tpacpi::kbd_backlight" in leds:
    kbd = "tpacpi::kbd_backlight"


class Brightness(Service):
    def __init__(self, **kwargs):
        self.screen_backlight_path = "/sys/class/backlight/" + SCREEN
        self.kbd_backlight_path = "/sys/class/leds/" + kbd
        self.max_kbd = -1
        self.max_screen = -1

        if os.path.exists(self.screen_backlight_path + "/max_brightness"):
            with open(self.screen_backlight_path + "/max_brightness") as f:
                self.max_screen = int(f.read())
            self.screen_monitor = monitor_file(
                self.screen_backlight_path + "/brightness"
            )

            self.screen_monitor.connect(
                "changed",
                lambda _, file, *args: self.notify("screen-brightness"),
            )

        if os.path.exists(self.kbd_backlight_path + "/max_brightness"):
            with open(self.kbd_backlight_path + "/max_brightness") as f:
                self.max_kbd = int(f.read())

        super().__init__(**kwargs)

    @Property(int, "read-write")
    def screen_brightness(self) -> int:  # type: ignore
        with open(self.screen_backlight_path + "/brightness") as f:
            brightness = int(f.readline())

        return brightness

    @screen_brightness.setter
    def screen_brightness(self, value: int):
        if value < 0 or value > self.max_screen:
            return
        try:
            exec_brightnessctl_async(f"--device '{SCREEN}' set {value}")
        except GLib.Error as e:
            print(e.message)

    @Property(int, "read-write")
    def keyboard_brightness(self) -> int:  # type: ignore
        with open(self.kbd_backlight_path + "/brightness") as f:
            brightness = int(f.readline())
        return brightness

    @keyboard_brightness.setter
    def keyboard_brightness(self, value):
        if value < 0 or value > self.max_kbd:
            return
        try:
            exec_brightnessctl_async(f"--device '{kbd}' set {value}")
        except GLib.Error as e:
            print(e.message)
