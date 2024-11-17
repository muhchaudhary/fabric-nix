import math
import cairo
from typing import cast
from fabric.widgets.image import Image
from gi.repository import Gtk


class RotatableImage(Image):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._angle = 0
        self.og_width = self.get_pixbuf().get_width()
        self.og_height = self.get_pixbuf().get_height()

    def set_angle(self, angle: int):
        self._angle = angle
        angle_rad = self._angle * math.pi / 180
        width = self.og_width
        height = self.og_height

        new_width = abs(width * math.cos(angle_rad)) + abs(height * math.sin(angle_rad))
        new_height = abs(width * math.sin(angle_rad)) + abs(
            height * math.cos(angle_rad)
        )
        self.set_size_request(new_width, new_height)

    def do_render_rectangle(
        self, cr: cairo.Context, width: int, height: int, radius: int = 0
    ):
        cr.move_to(0, 0)
        cr.line_to(width, 0)
        cr.line_to(width, height)
        cr.line_to(0, height)
        cr.line_to(0, 0)
        cr.close_path()

    def do_rotate_rectangle(self, ctx: cairo.Context, width: int, height: int):
        angle_rad = self._angle * math.pi / 180
        ctx.translate(self.get_allocated_width() / 2, self.get_allocated_height() / 2)
        ctx.rotate(angle_rad)
        ctx.translate(-width / 2, -height / 2)

    def do_draw(self, cr: cairo.Context):
        width, height = self.get_allocated_width(), self.get_allocated_height()
        cr.save()

        self.do_render_rectangle(
            cr,
            width,
            height,
        )

        self.do_rotate_rectangle(cr, width, height)
        cr.clip()
        Image.do_draw(self, cr)

        cr.restore()
