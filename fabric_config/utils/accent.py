from typing import Callable

from PIL import Image

from fabric_config.utils import image_worker


def dominant_color(image_path: str) -> tuple[int, int, int]:
    """The most common colour of an image file (see `dominant_color_of`)."""
    with Image.open(image_path) as image:
        image.draft("RGB", (256, 256))  # JPEG decodes straight to a smaller size
        # shrink before converting: a full-size conversion is another copy
        image.thumbnail((96, 96))
        return dominant_color_of(image.convert("RGB"))


def dominant_color_of(image: Image.Image) -> tuple[int, int, int]:
    """
    The most common colour of an image, cheaply: shrink it and let Pillow's C
    quantizer do the work. (ColorThief, used before, is pure Python and held
    the GIL for most of a second on a 4K wallpaper, freezing the GTK loop.)
    """
    if image.width > 96 or image.height > 96:
        image = image.copy()
        image.thumbnail((96, 96))
    palette_image = image.quantize(colors=5, method=Image.Quantize.MEDIANCUT)
    colors = palette_image.getcolors() or [(1, 0)]
    # palette images report (count, palette index) pairs
    index = int(max(colors, key=lambda c: c[0])[1])  # type: ignore[arg-type]
    palette = palette_image.getpalette() or [0, 0, 0]
    r, g, b = palette[index * 3 : index * 3 + 3]
    return r, g, b


def grab_dominant_color_threaded(image_path: str, callback: Callable):
    """`dominant_color` on the image worker; calls back on the main loop
    (`None` when the file can't be read)."""
    image_worker.submit(lambda: dominant_color(image_path), callback)


def grab_wallpaper_color(path: str, callback: Callable):
    """Like `grab_dominant_color_threaded`, sharing the wallpaper's decode
    with the other wallpaper measurements."""
    image_worker.submit(
        lambda: dominant_color_of(image_worker.open_reduced(path)), callback
    )
