from typing import Callable
from PIL import Image
import threading

from loguru import logger
from gi.repository import GLib


def dominant_color(image_path: str) -> tuple[int, int, int]:
    """
    The most common colour of an image, cheaply: decode at reduced size and
    let Pillow's C quantizer do the work. (ColorThief, used before, is pure
    Python and held the GIL for most of a second on a 4K wallpaper, freezing
    the GTK loop.)
    """
    image = Image.open(image_path)
    image.draft("RGB", (256, 256))  # JPEG decodes straight to a smaller size
    image = image.convert("RGB")
    image.thumbnail((96, 96))
    palette_image = image.quantize(colors=5, method=Image.Quantize.MEDIANCUT)
    colors = palette_image.getcolors() or [(1, 0)]
    # palette images report (count, palette index) pairs
    index = int(max(colors, key=lambda c: c[0])[1])  # type: ignore[arg-type]
    palette = palette_image.getpalette() or [0, 0, 0]
    r, g, b = palette[index * 3 : index * 3 + 3]
    return r, g, b


def grab_dominant_color_threaded(image_path: str, callback: Callable):
    """`dominant_color` off the main thread; calls back on the main loop."""

    def thread_function():
        try:
            color = dominant_color(image_path)
        except Exception as e:
            logger.error(f"[COLORS] Failed to read {image_path}: {e}")
            color = None
        GLib.idle_add(callback, color)

    threading.Thread(target=thread_function, daemon=True).start()
