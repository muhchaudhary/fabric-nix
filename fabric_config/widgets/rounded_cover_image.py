import math
from typing import Literal

import cairo
from gi.repository import Gdk, GdkPixbuf, Gtk


class RoundedCoverImage(Gtk.DrawingArea):
    """
    An image with rounded corners that fills its allocation.

    The pixbuf is scaled to cover the whole area and centre-cropped (like CSS
    `object-fit: cover`), so the widget keeps its size whatever the image's
    aspect ratio. GTK3 CSS `border-radius` doesn't clip image content, so the
    rounding is done here with a cairo clip. Until a pixbuf is set, a
    placeholder is drawn.

    Pass width=-1 to fill the available width (set h_expand on the widget).

    fit="contain" instead shows the whole image, scaled down to fit (never
    enlarged), centred on a subtle backdrop: better when the content matters
    more than filling the area.
    """

    def __init__(
        self,
        width: int,
        height: int,
        radius: float = 12,
        fit: Literal["cover", "contain"] = "cover",
    ):
        super().__init__()
        self._radius = radius
        self._fit = fit
        self._pixbuf: GdkPixbuf.Pixbuf | None = None
        # scaled surface cached for one (width, height, scale factor)
        self._surface: cairo.Surface | None = None
        self._surface_key: tuple[int, int, int] | None = None
        self._surface_size: tuple[float, float] = (0, 0)

        self.set_size_request(width, height)
        self.get_style_context().add_class("rounded-cover-image")
        self.connect("draw", self._on_draw)
        self.show()

    def set_pixbuf(self, pixbuf: GdkPixbuf.Pixbuf | None):
        self._pixbuf = pixbuf
        self._surface = None
        self._surface_key = None
        self.queue_draw()

    def _rounded_rect(self, cr: cairo.Context, w: float, h: float, r: float):
        cr.new_sub_path()
        cr.arc(w - r, r, r, -math.pi / 2, 0)
        cr.arc(w - r, h - r, r, 0, math.pi / 2)
        cr.arc(r, h - r, r, math.pi / 2, math.pi)
        cr.arc(r, r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

    def _get_surface(self, width: int, height: int) -> cairo.Surface | None:
        if self._pixbuf is None or width <= 0 or height <= 0:
            return None
        scale = self.get_scale_factor()
        key = (width, height, scale)
        if self._surface is not None and self._surface_key == key:
            return self._surface

        src_w, src_h = self._pixbuf.get_width(), self._pixbuf.get_height()
        if self._fit == "contain":
            # whole image, at most its natural size (in logical pixels)
            factor = min(width / src_w, height / src_h, 1.0) * scale
            draw_w = max(1, round(src_w * factor))
            draw_h = max(1, round(src_h * factor))
            scaled = self._pixbuf.scale_simple(
                draw_w, draw_h, GdkPixbuf.InterpType.BILINEAR
            )
            self._surface = Gdk.cairo_surface_create_from_pixbuf(
                scaled, scale, self.get_window()
            )
            self._surface_key = key
            self._surface_size = (draw_w / scale, draw_h / scale)
            return self._surface

        # cover-fit at device resolution so images stay sharp on HiDPI screens
        target_w, target_h = width * scale, height * scale
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
        self._surface_key = key
        self._surface_size = (width, height)
        return self._surface

    def _on_draw(self, _widget, cr: cairo.Context):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        self._rounded_rect(cr, w, h, min(self._radius, w / 2, h / 2))
        cr.clip()

        surface = self._get_surface(w, h)
        if surface is None:
            # placeholder while the thumbnail is generated or loaded
            color = self.get_style_context().get_color(Gtk.StateFlags.NORMAL)
            cr.set_source_rgba(color.red, color.green, color.blue, 0.08)
            cr.paint()
            return False

        if self._fit == "contain":
            # backdrop behind letterboxed images
            color = self.get_style_context().get_color(Gtk.StateFlags.NORMAL)
            cr.set_source_rgba(color.red, color.green, color.blue, 0.06)
            cr.paint()
        draw_w, draw_h = self._surface_size
        cr.set_source_surface(surface, (w - draw_w) / 2, (h - draw_h) / 2)
        cr.paint()
        return False
