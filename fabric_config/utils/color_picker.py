from fabric.core.service import Service, Signal
from gi.repository import GLib
from loguru import logger

from fabric_config.utils.process import run_command_async


class ColorPicker(Service):
    @Signal
    def picked(self, color: str) -> None:
        """A colour was picked and copied (hex, e.g. #ff8800)."""


# whoever wants to know about picks (the bar's island) connects here
color_picker = ColorPicker()


def pick_color(delay_ms: int = 0):
    """Pick a colour with hyprpicker, copy its hex code and say so.

    `delay_ms` gives a closing popup time to leave the screen first.
    """

    def on_picked(success: bool, stdout: str, stderr: str):
        color = stdout.strip()
        if not success or not color:
            # Escape cancels the picker; that's not worth a warning
            if stderr.strip():
                logger.warning(f"[Colour picker] hyprpicker: {stderr.strip()}")
            return
        run_command_async(["wl-copy", "--", color])
        color_picker.picked(color)
        run_command_async(
            [
                "notify-send",
                "-a",
                "Colour Picker",
                "-i",
                "color-select-symbolic",
                f"Copied {color}",
            ]
        )

    def start():
        run_command_async(["hyprpicker", "-f", "hex"], on_picked)
        return False

    if delay_ms:
        GLib.timeout_add(delay_ms, start)
    else:
        start()
