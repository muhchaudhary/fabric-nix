import os

from fabric.core.service import Service, Property
from fabric.utils import exec_shell_command_async, monitor_file
from gi.repository import GLib
from loguru import logger


def exec_brightnessctl_async(args: str):
    exec_shell_command_async(f"brightnessctl {args}", lambda _: None)


SCREEN = os.listdir("/sys/class/backlight")
if SCREEN:
    SCREEN = SCREEN[0]
else:
    SCREEN = ""
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
        # dragging a slider sets the value many times a second; only the latest
        # value is applied, at most once per throttle interval
        self._pending_screen_value: int | None = None
        self._screen_throttle_id: int | None = None

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
        if os.path.exists(self.screen_backlight_path + "/brightness"):
            with open(self.screen_backlight_path + "/brightness") as f:
                brightness = int(f.readline())

            return brightness
        return -1

    @screen_brightness.setter
    def screen_brightness(self, value: int):
        if value < 0 or value > self.max_screen:
            return
        self._pending_screen_value = int(value)
        if self._screen_throttle_id is None:
            self._apply_pending_screen_brightness()
            self._screen_throttle_id = GLib.timeout_add(
                50, self._on_screen_throttle_timeout
            )

    def _apply_pending_screen_brightness(self):
        value, self._pending_screen_value = self._pending_screen_value, None
        if value is None:
            return
        try:
            exec_brightnessctl_async(f"--device '{SCREEN}' set {value}")
        except GLib.Error as e:
            logger.error(f"[Brightness] {e.message}")

    def _on_screen_throttle_timeout(self):
        if self._pending_screen_value is None:
            self._screen_throttle_id = None
            return False
        self._apply_pending_screen_brightness()
        return True

    @Property(int, "read-write")
    def keyboard_brightness(self) -> int:  # type: ignore
        if not kbd:
            return -1
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
            logger.error(f"[Brightness] {e.message}")
