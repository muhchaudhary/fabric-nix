import os

from fabric.service import Property, Service, Signal, SignalContainer
from fabric.utils import exec_shell_command, exec_shell_command_async, monitor_file
from gi.repository import GLib

# In the future, use GUdev to get ehe brightness devices


# BUG This will open a new file every single time for some
#     reason, seems like brightnessctil does not stop function after completion
def exec_brightnessctl_async(args: str):
    exec_shell_command_async(f"brightnessctl {args}", None)


screen = str(exec_shell_command("ls -w1 /sys/class/backlight")).split("\n")[0]
leds = str(exec_shell_command("ls -w1 /sys/class/leds")).split("\n")

kbd = ""
if "tpacpi::kbd_backlight" in leds:
    kbd = "tpacpi::kbd_backlight"


class NoBrightnessError(ImportError):
    def __init__(self, *args):
        super().__init__(
            "Playerctl is not installed, please install it first",
            *args,
        )


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
            with open(self.screen_backlight_path + "/max_brightness") as f:
                self.max_screen = int(f.read())
        if os.path.exists(self.kbd_backlight_path + "/max_brightness"):
            with open(self.kbd_backlight_path + "/max_brightness") as f:
                self.max_kbd = int(f.read())

        self.screen_monitor = monitor_file(self.screen_backlight_path + "/brightness")
        self.screen_monitor.connect(
            "changed",
            lambda _, file, *args: self.emit(
                "screen",
                round(int(file.load_bytes()[0].get_data())),
            ),
        )
        super().__init__(**kwargs)

    @Property(value_type=int, flags="read-write")
    def screen_brightness(self) -> int:
        return (
            int(
                os.read(
                    os.open(self.screen_backlight_path + "/brightness", os.O_RDONLY), 6
                ),
            )
            if os.path.exists(self.screen_backlight_path + "/brightness")
            else -1
        )

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
        if not kbd:
            return -1
        if value < 0 or value > self.max_kbd:
            return None
        try:
            exec_brightnessctl_async(f"--device '{kbd}' set {value}")
            self.emit("kbd", value)
        except GLib.Error as e:
            print(e.message)
