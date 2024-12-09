from typing import Callable
from colorthief import ColorThief
import threading

from loguru import logger
from gi.repository import GLib


def grab_accent_color_threaded(
    image_path: str,
    callback: Callable,
    quality: int = 10,
):
    def thread_function():
        try:
            ct = ColorThief(file=image_path).get_color(quality)
            GLib.idle_add(callback, ct)
        except Exception:
            logger.error("[COLORS] Failed to grab an accent color")
            GLib.idle_add(callback, None)
        finally:
            GLib.idle_add(thread.join)

    thread = threading.Thread(target=thread_function)
    thread.start()


def grab_color(image_path: str, n: int):
    c_t = ColorThief(image_path)
    return c_t.get_color(n)
