import math

import cairo
from gi.repository import Gdk, GdkPixbuf, Gtk


class WallpaperTile(Gtk.DrawingArea):
    """
    A fixed-size image tile with rounded corners.

    The pixbuf is scaled to cover the whole tile and centre-cropped (like CSS
    `object-fit: cover`), so every tile has the same size whatever the image's
    aspect ratio. GTK3 CSS `border-radius` doesn't clip image content, so the
    rounding is done here with a cairo clip. Until a pixbuf is set, a
    placeholder is drawn.
    """

    def __init__(self, width: int, height: int, radius: float = 12):
        super().__init__()
        self._width = width
        self._height = height
        self._radius = radius
        self._pixbuf: GdkPixbuf.Pixbuf | None = None
        # scaled surface cached per device scale factor
        self._surface: cairo.Surface | None = None
        self._surface_scale = 0

        self.set_size_request(width, height)
        self.get_style_context().add_class("wallpaper-tile")
        self.connect("draw", self._on_draw)
        self.show()

    def set_pixbuf(self, pixbuf: GdkPixbuf.Pixbuf | None):
        self._pixbuf = pixbuf
        self._surface = None
        self.queue_draw()

    def _rounded_rect(self, cr: cairo.Context, w: float, h: float, r: float):
        cr.new_sub_path()
        cr.arc(w - r, r, r, -math.pi / 2, 0)
        cr.arc(w - r, h - r, r, 0, math.pi / 2)
        cr.arc(r, h - r, r, math.pi / 2, math.pi)
        cr.arc(r, r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

    def _get_surface(self) -> cairo.Surface | None:
        if self._pixbuf is None:
            return None
        scale = self.get_scale_factor()
        if self._surface is not None and self._surface_scale == scale:
            return self._surface

        # cover-fit at device resolution so tiles stay sharp on HiDPI screens
        target_w, target_h = self._width * scale, self._height * scale
        src_w, src_h = self._pixbuf.get_width(), self._pixbuf.get_height()
        factor = max(target_w / src_w, target_h / src_h)
        scaled_w = max(target_w, math.ceil(src_w * factor))
        scaled_h = max(target_h, math.ceil(src_h * factor))
        scaled = self._pixbuf.scale_simple(
            scaled_w, scaled_h, GdkPixbuf.InterpType.BILINEAR
        )
        cropped = scaled.new_subpixbuf(
            (scaled_w - target_w) // 2,
            (scaled_h - target_h) // 2,
            target_w,
            target_h,
        )
        self._surface = Gdk.cairo_surface_create_from_pixbuf(
            cropped, scale, self.get_window()
        )
        self._surface_scale = scale
        return self._surface

    def _on_draw(self, _widget, cr: cairo.Context):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        self._rounded_rect(cr, w, h, min(self._radius, w / 2, h / 2))
        cr.clip()

        surface = self._get_surface()
        if surface is None:
            # placeholder while the thumbnail is generated or loaded
            color = self.get_style_context().get_color(Gtk.StateFlags.NORMAL)
            cr.set_source_rgba(color.red, color.green, color.blue, 0.08)
            cr.paint()
            return False

        cr.set_source_surface(surface, 0, 0)
        cr.paint()
        return False
