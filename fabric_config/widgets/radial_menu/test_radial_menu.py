import math
from operator import index
from typing import Iterable, List, Literal

import cairo
import gi
from fabric import Application
from fabric.widgets.wayland import WaylandWindow as Window
from fabric.widgets.widget import Widget
from fabric.widgets.image import Image
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from animator import Animator

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk


def polar_to_cartesian(x, y, angle, r):
    return x + r * math.cos(angle), y + r * math.sin(angle)


class RadialMenuSegment(Widget):
    def __init__(
        self,
        child: Widget | None = None,
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
        self.child = child
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

class RadialMenuDrawingArea(Gtk.DrawingArea, Widget):
    def __init__(
        self,
        # Radial menu specific props
        children: List[RadialMenuSegment],
        center_child: Widget | None = None,
        # end
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
        self.children_segments = children
        self.center_child = center_child
        self.num_segments = len(self.children_segments)
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
        self.set_size_request(
            self.width, self.height
        )

        print(self.width, self.height)
        self.center_x = (self.width) / 2
        self.center_y = (self.height) / 2
        self.radius = self.height / 2
        self.outer_radius = self.radius
        self.inner_radius = self.radius / 3

    def on_draw(self, _, cr: cairo.Context):
        self.get_style_ctx()

        for i in range(self.num_segments):
            self.draw_segment(cr, i, self.outer_radius, self.inner_radius)

    def draw_segment(self, cr: cairo.Context, index, outer_radius, inner_radius):
        cr.new_path()

        # Set State
        state = self.children_segments[index].get_state_flags()

        if self.hovered_segment == index:
            if not (state & Gtk.StateFlags.PRELIGHT):
                self.children_segments[index].set_state_flags(
                    Gtk.StateFlags.PRELIGHT, False
                )
        else:
            if state & Gtk.StateFlags.PRELIGHT:
                self.children_segments[index].unset_state_flags(Gtk.StateFlags.PRELIGHT)


        state = self.children_segments[index].get_state_flags()

        # Apply State
        p = max(
            (
                padding := self.get_segment_style(index).get_padding(
                    self.children_segments[index].get_state_flags()
                )
            ).top,
            padding.bottom,
            padding.left,
            padding.right,
        )
        inner_radius += p
        outer_radius -= p

        border = max(
            (
                border := self.get_segment_style(index).get_border(
                    self.children_segments[index].get_state_flags()
                )
            ).top,
            border.bottom,
            border.left,
            border.right,
        )
        cr.set_line_width(border)

        Gdk.cairo_set_source_rgba(
            cr,
            self.get_segment_style(index).get_property(
                "background-color", self.children_segments[index].get_state_flags()
            ),
        )

        inner_theta = math.atan(p / (inner_radius))
        outer_theta = math.atan(p / (outer_radius))

        start_outer_angle = index * ((2 * math.pi) / self.num_segments) + outer_theta
        end_outer_angle = (index + 1) * (
            (2 * math.pi) / self.num_segments
        ) - outer_theta

        start_inner_angle = index * ((2 * math.pi) / self.num_segments) + inner_theta
        end_inner_angle = (index + 1) * (
            (2 * math.pi) / self.num_segments
        ) - inner_theta
        cr.arc(
            self.center_x,
            self.center_y,
            outer_radius,
            start_outer_angle,
            end_outer_angle,
        )
        cr.arc_negative(
            self.center_x,
            self.center_y,
            inner_radius,
            end_inner_angle,
            start_inner_angle,
        )
        cr.close_path()
        cr.fill_preserve()
        Gdk.cairo_set_source_rgba(
            cr,
            self.get_segment_style(index).get_property(
                "border-color", self.children_segments[index].get_state_flags()
            ),
        )
        cr.stroke()

    def on_motion(self, widget, event):
        segment = self.get_segment(event.x, event.y)
        if segment != self.hovered_segment:
            self.hovered_segment = segment
            self.queue_draw()

    def on_click(self, widget, event):
        segment = self.get_segment(event.x, y=event.y)
        if segment is not None:
            print(f"Segment {segment} clicked")
            self.queue_draw()
        
        self.set_state_flags(Gtk.StateFlags.PRELIGHT, False)


    def get_segment(self, x, y):
        dx, dy = x - self.center_x, y - self.center_y
        distance = math.sqrt(dx**2 + dy**2)

        if distance > self.radius or distance < self.inner_radius:
            return None

        angle = math.atan2(dy, dx)
        if angle < 0:
            angle += 2 * math.pi

        return int(angle / ((2 * math.pi) / self.num_segments))

    def get_segment_style(self, index: int):
        return self.children_segments[index].get_style_context()


class RadialMenu(Gtk.Fixed, Widget):
    def __init__(
        self,
        # Radial menu specific props
        children: List[RadialMenuSegment],
        center_child: Widget | None = None,
        # end
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
        Gtk.Fixed.__init__(self)
        Widget.__init__(
            self,
            None,
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
        self.drawing_area = RadialMenuDrawingArea(
            children,
            center_child,
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
        self.children_segments = children
        self.center_child = center_child
        super().put(self.drawing_area, 0, 0)
        self.drawing_area.connect("size-allocate", self.on_size_allocate)
    
    def on_size_allocate(self, _, __):
        print("Size allocated, moving widgets")
        self.move_widgets()

    def move_widgets(self):
        for i in range(len(self.children_segments)):
            self.move_segment_child(i)
        if self.center_child is not None:
            child_size = self.center_child.get_preferred_size()
            if self.center_child in super().get_children():
                super().move(
                    self.center_child,
                    self.drawing_area.outer_radius - child_size.natural_size.width / 2,
                    self.drawing_area.center_y - child_size.natural_size.height / 2,
                )
                return
            super().put(
                self.center_child,
                self.drawing_area.center_x - child_size.natural_size.width / 2,
                self.drawing_area.center_y - child_size.natural_size.height / 2,
            )

    def move_segment_child(self, i: int):
        child = self.children_segments[i].child
        if child is None:
            return
        angle_step = (2 * math.pi) / len(self.children_segments)
        start_angle = i * angle_step
        end_angle = (i + 1) * angle_step

        child_size = child.get_preferred_size()
        segment_center_x, segment_center_y = polar_to_cartesian(
            self.drawing_area.center_x,
            self.drawing_area.center_y,
            (start_angle + end_angle) / 2,
            (self.drawing_area.outer_radius + self.drawing_area.inner_radius) / 2,
        )
        if child in super().get_children():
            super().move(
                child,
                segment_center_x - child_size.natural_size.width / 2,
                segment_center_y - child_size.natural_size.height / 2,
            )
            return
        super().put(
            child,
            segment_center_x - child_size.natural_size.width / 2,
            segment_center_y - child_size.natural_size.height / 2,
        )


radial_children = [
    RadialMenuSegment(
        name=f"radial-segment-{i}",
        child=Box(
            orientation="vertical",
            children=[
                Image(
                    image_file="/home/muhammad/Pictures/bolt.png",
                    size=(100, -1),
                ),
                Label(f"Item {i}", style="color: black; font-size: 30px;"),
            ],
        ),
    )
    for i in range(1, 5)
]

menu = RadialMenu(
    name="radial-menu",
    children=radial_children,
    center_child=Image(
        image_file="/home/muhammad/Pictures/bolt.png",
        size=(150, 150),
    ),
)
win = Window(
    layer="overlay",
    child=menu,
    anchor="center",
    style="background-color: unset;",
)

app = Application()
app.set_stylesheet_from_file(
    "/home/muhammad/nixOS/fabric/fabric_config/widgets/radial_menu/test_style.css"
)

app.run()
