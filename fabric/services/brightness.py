import os
from fabric.service import Service, Signal, SignalContainer, Property
from fabric.utils import exec_shell_command, monitor_file
from gi.repository import GLib


def exec_brightnessctl(args: str):
    return exec_shell_command(f"brightnessctl {args}")


def exec_brightnessctl_async(args: str):
    return GLib.spawn_command_line_async(f"brightnessctl {args}")


screen = str(exec_shell_command("ls -w1 /sys/class/backlight")).split("\n")[0]
leds = str(exec_shell_command("ls -w1 /sys/class/leds")).split("\n")

kbd = ""

if "tpacpi::kbd_backlight" in leds:
    kbd = "tpacpi::kbd_backlight"


class Brightness(Service):
    __gsignals__ = SignalContainer(
        Signal("screen", "run-first", None, (int,)),
        Signal("kbd", "run-first", None, (int,)),
    )

    def __init__(self, **kwargs):
        self.screen_backlight_path = "/sys/class/backlight/" + screen
        self.kbd_backlight_path = "/sys/class/leds/" + kbd
        self.max_kbd = -1
        self.max_screen = -1

        if os.path.exists(self.screen_backlight_path + "/max_brightness"):
            with open(self.screen_backlight_path + "/max_brightness", "r") as f:
                self.max_screen = int(f.read())

        if os.path.exists(self.kbd_backlight_path + "/max_brightness"):
            with open(self.kbd_backlight_path + "/max_brightness", "r") as f:
                self.max_kbd = int(f.read())

        self.screen_monitor = monitor_file(self.screen_backlight_path + "/brightness")
        self.screen_monitor.connect(
            "changed",
            lambda _, file, *args: self.emit("screen", round(int(file.load_bytes()[0].get_data()))),
        )
        super().__init__(**kwargs)

    @Property(value_type=int, flags="read-write")
    def screen_brightness(self) -> int:
        return int(exec_brightnessctl(f"--device '{screen}' get"))

    @screen_brightness.setter
    def screen_brightness(self, value: int):
        if value < 0 or value > self.max_screen:
            return 0 if value < 0 else self.max_screen
        try:
            exec_brightnessctl_async(f"--device '{screen}' set {value}")
            self.emit("screen", int((value / self.max_screen) * 100))
        except GLib.Error as e:
            print(e.message)

    def set_kbd(self, value: int):
        if value < 0 or value > self.max_kbd:
            return
        try:
            exec_brightnessctl_async(f"--device '{kbd}' set {value}")
            self.emit("kbd", value)
        except GLib.Error as e:
            print(e.message)

