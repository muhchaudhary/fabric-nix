import math
from typing import Literal

import cairo
import gi
from fabric.widgets.widget import Widget

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gtk  # noqa: E402


class CircleImage(Gtk.DrawingArea, Widget):
    def __init__(
        self,
        image_file: str | None = None,
        pixel_size: int | tuple[int] | None = None,
        visible: bool = True,
        all_visible: bool = False,
        style: str | None = None,
        style_compiled: bool = True,
        style_append: bool = False,
        style_add_brackets: bool = True,
        tooltip_text: str | None = None,
        transition_type: str | None = "None",
        tooltip_markup: str | None = None,
        h_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        v_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        h_expand: bool = False,
        v_expand: bool = False,
        name: str | None = None,
        size: int = 144,
        **kwargs,
    ):
        Gtk.DrawingArea.__init__(
            self,
            **(self.do_get_filtered_kwargs(kwargs)),
        )
        Widget.__init__(
            self,
            visible,
            all_visible,
            style,
            style_compiled,
            style_append,
            style_add_brackets,
            tooltip_text,
            tooltip_markup,
            h_align,
            v_align,
            h_expand,
            v_expand,
            name,
            None,
        )

        self.transition_type = transition_type
        self.image_file = image_file
        self.rotation = 0
        self.size: int = size
        self.image = (
            GdkPixbuf.Pixbuf.new_from_file_at_size(
                self.image_file,
                -1,
                self.size,
            )
            if self.image_file is not None
            else None
        )
        self.set_size_request(self.size, self.size)
        self.do_connect_signals_for_kwargs(kwargs)
        self.connect("draw", self.draw)

    def draw(self, wdiget: Gtk.DrawingArea, ctx: cairo.Context):
        ctx.save()
        ctx.arc(self.size / 2, self.size / 2, self.size / 2, 0, 2 * math.pi)
        ctx.translate(self.size * 0.5, self.size * 0.5)
        ctx.rotate(self.rotation * math.pi / 180.0)
        ctx.translate(
            -self.size * 0.5
            - self.image.get_width() // 2
            + self.image.get_height() // 2,
            -self.size * 0.5,
        )
        Gdk.cairo_set_source_pixbuf(ctx, self.image, 0, 0) if self.image else None
        ctx.clip()
        ctx.paint()
        ctx.restore()

    def rotate_more(self, rot):
        direction = 1 if self.transition_type == "negbezier" else -1

        self.rotation = direction * rot
        self.queue_draw()

    def set_transition_type(self, new_transition):
        self.transition_type = new_transition

    def set_image(self, new_image_file):
        if new_image_file == "":
            return
        self.image = (
            GdkPixbuf.Pixbuf.new_from_file_at_size(
                new_image_file,
                -1,
                self.size,
            )
            if self.image_file is not None
            else None
        )
        self.queue_draw()

    def do_calculate_new_size(
        self, base_width, base_height, desired_width, desired_height,
    ):
        try:
            aspect_ratio = base_width / base_height
            new_width = aspect_ratio * desired_height
            if new_width > desired_width:
                new_width = desired_width
                new_height = desired_width / aspect_ratio
            else:
                new_height = desired_height
        except ZeroDivisionError:
            new_width = desired_width
            new_height = desired_height
        return new_width, new_height
