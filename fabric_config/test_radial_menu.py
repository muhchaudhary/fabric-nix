import math
from typing import Iterable, Literal

import cairo
import gi
from fabric import Application
from fabric.widgets.wayland import WaylandWindow as Window
from fabric.widgets.widget import Widget

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk


def polar_to_cartesian(x, y, angle, r):
    return x + r * math.cos(angle), y + r * math.sin(angle)


class RadialMenu(Gtk.DrawingArea, Widget):
    def __init__(
        self,
        name: str | None = None,
        visible: bool = True,
        all_visible: bool = False,
        style: str | None = None,
        style_classes: Iterable[str] | str | None = None,
        tooltip_text: str | None = None,
        tooltip_markup: str | None = None,
        h_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        v_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        h_expand: bool = False,
        v_expand: bool = False,
        size: Iterable[int] | int | None = None,
        **kwargs,
    ):
        Gtk.DrawingArea.__init__(self)
        Widget.__init__(
            self,
            name,
            visible,
            all_visible,
            style,
            style_classes,
            tooltip_text,
            tooltip_markup,
            h_align,
            v_align,
            h_expand,
            v_expand,
            size,
            **kwargs,
        )

        self.num_segments = 3
        self.get_style_ctx()
        self.hovered_segment = None

        self.connect("draw", self.on_draw)
        self.add_events(
            [Gdk.EventMask.BUTTON_PRESS_MASK, Gdk.EventMask.POINTER_MOTION_MASK]
        )
        self.connect("button-press-event", self.on_click)
        self.connect("motion-notify-event", self.on_motion)

    def get_style_ctx(self):
        style_context = self.get_style_context()
        self.width: int = style_context.get_property("min-width", Gtk.StateFlags.NORMAL)  # type: ignore
        self.height: int = style_context.get_property(
            "min-height", Gtk.StateFlags.NORMAL
        )  # type: ignore
        self.segment_padding = 15
        self.set_size_request(
            self.width + self.segment_padding, self.height + self.segment_padding
        )
        self.center_x = (self.width + self.segment_padding) / 2
        self.center_y = (self.height + self.segment_padding) / 2
        self.radius = self.height / 2 - 20
        self.outer_radius = self.radius
        self.inner_radius = self.radius / 3
        # TODO do not hardcode padding
        self.padding = 15
        self.padding_angle = math.radians(self.padding)

    def draw_text(self, cr: cairo.Context, segment_index, start_angle, end_angle):
        cr.set_source_rgb(1, 1, 1)
        cr.set_font_size(32)
        segment_center = polar_to_cartesian(
            self.center_x,
            self.center_y,
            (start_angle + end_angle) / 2,
            (self.outer_radius + self.inner_radius) / 2,
        )
        cr.move_to(*segment_center)
        cr.show_text(f"{segment_index}")

    def on_draw(self, widget, cr: cairo.Context):
        self.get_style_ctx()
        cr.set_line_width(8)

        angle_step = (2 * math.pi) / self.num_segments

        cr.set_source_rgb(1, 1, 1)
        cr.set_font_size(32)
        text = cr.text_extents(f"Segment {self.hovered_segment}")
        cr.move_to(self.center_x, self.center_y)
        cr.rel_move_to(-text.width / 2, text.height / 2)
        cr.show_text(f"Segment {self.hovered_segment}")

        for i in range(self.num_segments):
            start_angle = i * angle_step
            end_angle = (i + 1) * angle_step
            # self.draw_segment(
            #     cr,
            #     start_angle,
            #     end_angle,
            #     i,
            # )
            self.draw_segment_v2(cr, i, self.outer_radius, self.inner_radius)
            self.draw_text(cr, i, start_angle, end_angle)

    def draw_segment_v2(self, cr: cairo.Context, index, outer_radius, inner_radius):
        p = 5

        inner_theta1 = math.atan((inner_radius + p) / p)
        outer_theta1 = math.atan((outer_radius - p) / p)

        inner_theta2 = math.atan(p / (inner_radius + p))
        outer_theta2 = math.atan(p / (inner_radius - p))

        cr.new_path()
        if self.hovered_segment == index:
            cr.set_source_rgb(209 / 256, 100 / 256, 42 / 256)
            self.padding_angle = math.radians(0)
            self.padding = 0
        else:
            cr.set_source_rgb(47 / 256, 90 / 256, 130 / 256)

        start_outer_angle = index * ((2 * math.pi) / self.num_segments)
        end_outer_angle = (index + 1) * (2 * math.pi) / self.num_segments
        start_outer = polar_to_cartesian(
            self.center_x, self.center_y, start_outer_angle, outer_radius
        )
        end_outer = polar_to_cartesian(
            self.center_x, self.center_y, end_outer_angle, outer_radius
        )
        start_inner = polar_to_cartesian(
            self.center_x, self.center_y, start_outer_angle, inner_radius
        )
        end_inner = polar_to_cartesian(
            self.center_x, self.center_y, end_outer_angle, inner_radius
        )
        cr.move_to(*start_inner)
        cr.line_to(*start_outer)
        cr.arc(
            self.center_x,
            self.center_y,
            outer_radius,
            start_outer_angle,
            end_outer_angle,
        )
        cr.move_to(*end_outer)
        cr.line_to(*end_inner)
        cr.arc_negative(
            self.center_x,
            self.center_y,
            inner_radius,
            end_outer_angle,
            start_outer_angle,
        )
        cr.move_to(*start_inner)

        cr.close_path()
        cr.fill_preserve()
        cr.set_source_rgb(100 / 256, 90 / 256, 256 / 256)
        cr.stroke()

    def draw_arc_between_points(self, ctx, x1, y1, x2, y2, radius, clockwise=False):
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2

        dx = x2 - x1
        dy = y2 - y1
        length = math.sqrt(dx**2 + dy**2)

        if length == 0:
            return  # Avoid division by zero

        dx /= length  # Normalize
        dy /= length

        # Perpendicular vector (rotate by 90 degrees)
        perp_x = -dy
        perp_y = dx

        # Compute distance from midpoint to arc center using Pythagoras
        chord_length = length / 2
        if radius**2 < chord_length**2:
            print("Radius too small to form an arc")
            return

        height = math.sqrt(max(radius**2 - chord_length**2, 1))

        # Choose one of the two possible arc centers
        if clockwise:
            cx = mx - perp_x * height
            cy = my - perp_y * height
        else:
            cx = mx + perp_x * height
            cy = my + perp_y * height

        # Compute start and end angles
        start_angle = math.atan2(y1 - cy, x1 - cx)
        end_angle = math.atan2(y2 - cy, x2 - cx)

        # Draw the arc
        if clockwise:
            ctx.arc_negative(cx, cy, radius, start_angle, end_angle)
        else:
            ctx.arc(cx, cy, radius, start_angle, end_angle)

    def draw_segment(self, cr: cairo.Context, start_angle, end_angle, index):
        old_angle = self.padding_angle
        old_padding = self.padding
        if self.hovered_segment == index:
            cr.set_source_rgb(209 / 256, 100 / 256, 42 / 256)
            self.padding_angle = math.radians(0)
            self.padding = 0
        else:
            cr.set_source_rgb(47 / 256, 90 / 256, 130 / 256)

        border_radius = 10
        start_angle += 1 / 2 * self.padding_angle
        end_angle -= 1 / 2 * self.padding_angle

        inner_1 = polar_to_cartesian(
            self.center_x,
            self.center_y,
            start_angle,
            self.inner_radius + self.padding + border_radius,
        )

        outer_1 = polar_to_cartesian(
            self.center_x,
            self.center_y,
            start_angle,
            self.outer_radius - self.padding - border_radius,
        )

        outer_2 = polar_to_cartesian(
            self.center_x,
            self.center_y,
            end_angle,
            self.outer_radius - self.padding - border_radius,
        )

        inner_2 = polar_to_cartesian(
            self.center_x,
            self.center_y,
            end_angle,
            self.inner_radius + self.padding + border_radius,
        )

        cr.move_to(*inner_1)
        cr.line_to(*outer_1)

        outer_offset = math.radians(border_radius / 2) / 3

        self.draw_arc_between_points(
            cr,
            *outer_1,
            *polar_to_cartesian(
                self.center_x,
                self.center_y,
                start_angle + outer_offset,
                self.outer_radius - self.padding,
            ),
            border_radius,
            False,
        )

        cr.arc(
            self.center_x,
            self.center_y,
            self.outer_radius - self.padding,
            start_angle + outer_offset,
            end_angle - outer_offset,
        )

        self.draw_arc_between_points(
            cr,
            *polar_to_cartesian(
                self.center_x,
                self.center_y,
                end_angle - outer_offset,
                self.outer_radius - self.padding,
            ),
            *outer_2,
            border_radius,
            False,
        )

        cr.line_to(*outer_2)
        cr.line_to(*inner_2)

        inner_offset = math.radians(border_radius * math.pi / 15)

        self.draw_arc_between_points(
            cr,
            *inner_2,
            *polar_to_cartesian(
                self.center_x,
                self.center_y,
                end_angle - inner_offset,
                self.inner_radius + self.padding,
            ),
            border_radius,
            False,
        )

        cr.arc_negative(
            self.center_x,
            self.center_y,
            self.inner_radius + self.padding,
            end_angle - inner_offset,
            start_angle + inner_offset,
        )

        self.draw_arc_between_points(
            cr,
            *polar_to_cartesian(
                self.center_x,
                self.center_y,
                start_angle + inner_offset,
                self.inner_radius + self.padding,
            ),
            *inner_1,
            border_radius,
            False,
        )

        cr.close_path()
        cr.fill_preserve()
        cr.set_source_rgb(5 / 256, 250 / 256, 42 / 256)
        cr.stroke()

        self.padding_angle = old_angle
        self.padding = old_padding

    def on_motion(self, widget, event):
        segment = self.get_segment(event.x, event.y)
        if segment != self.hovered_segment:
            self.hovered_segment = segment
            self.queue_draw()

    def on_click(self, widget, event):
        segment = self.get_segment(event.x, y=event.y)
        if segment is not None:
            print(f"Segment {segment} clicked")
            if segment == 1:
                self.num_segments += 1
                self.queue_draw()
            elif segment == 2:
                self.num_segments -= 1
                self.queue_draw()

    def get_segment(self, x, y):
        dx, dy = x - self.center_x, y - self.center_y
        distance = math.sqrt(dx**2 + dy**2)

        if distance > self.radius or distance < self.inner_radius:
            return None

        angle = math.atan2(dy, dx)
        if angle < 0:
            angle += 2 * math.pi

        return int(angle / ((2 * math.pi) / self.num_segments))


win = Window(
    layer="overlay",
    child=RadialMenu(style="min-width: 1000px; min-height: 1000px;"),
    anchor="center",
    style="background-color: unset;",
)

app = Application()

app.run()
