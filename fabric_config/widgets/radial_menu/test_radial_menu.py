import math
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
from fabric.core import Signal

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk


def polar_to_cartesian(x, y, angle, r):
    return x + r * math.cos(angle), y + r * math.sin(angle)


class RadialMenuSegment(Widget):
    @Signal
    def clicked(self, is_clicked: bool) -> bool: ...

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

        self.animated_padding = 0.0
        self.is_animating = False

    def get_padding(self, state: Gtk.StateFlags):
        return max(
            (padding := self.get_style_context().get_padding(state)).top,
            padding.bottom,
            padding.left,
            padding.right,
        )

    def get_border(self, state: Gtk.StateFlags):
        return max(
            (border := self.get_style_context().get_border(state)).top,
            border.bottom,
            border.left,
            border.right,
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
        self.segments = children
        self.center_child = center_child
        self.hovered_segment = None
        self.previous_hovered = None

        # Weight shift parameters
        self.shift_distance = 3.0
        self.shift_offset_x = 0.0
        self.shift_offset_y = 0.0
        self.target_shift_x = 0.0
        self.target_shift_y = 0.0

        self._shift_start_x = 0.0
        self._shift_start_y = 0.0

        self.shift_animator = Animator(
            bezier_curve=(0.25, 1.2, 0.5, 1.0),
            duration=0.35,
            tick_widget=self,
        )
        self.shift_animator.connect("notify::value", self.on_shift_animate)

        self.get_style_ctx()

        self.segment_animators = []
        for i in range(len(self.segments)):
            hover_in = Animator(
                bezier_curve=(0.34, 1.56, 0.64, 1.0),
                duration=0.4,
                tick_widget=self,
            )
            hover_in.connect(
                "notify::value", lambda a, _, idx=i: self.on_segment_animate(idx, a)
            )

            hover_out = Animator(
                bezier_curve=(0.5, 1.8, 0.5, 1.0),
                duration=0.35,
                tick_widget=self,
            )
            hover_out.connect(
                "notify::value", lambda a, _, idx=i: self.on_segment_animate(idx, a)
            )

            self.segment_animators.append(
                {
                    "hover_in": hover_in,
                    "hover_out": hover_out,
                    "animating_type": None,  # 'in' or 'out'
                }
            )

        self.connect("draw", self.on_draw)

        self.add_events(
            [Gdk.EventMask.BUTTON_PRESS_MASK, Gdk.EventMask.POINTER_MOTION_MASK]
        )
        self.connect("button-press-event", self.on_click)
        self.connect("motion-notify-event", self.on_motion)

    def get_style_ctx(self):
        # TODO: allow the user to choose inner radius just like they can choose size
        style_context = self.get_style_context()
        self.size = max(
            style_context.get_property("min-width", style_context.get_state()),
            style_context.get_property("min-height", style_context.get_state()),
        )
        self.set_size_request(
            self.size + self.shift_distance * 2, self.size + self.shift_distance * 2
        )

        self.center_x = (self.size / 2) + self.shift_distance
        self.center_y = (self.size / 2) + self.shift_distance

        self.outer_radius = self.size / 2
        self.inner_radius = self.outer_radius / 2.5

    def on_draw(self, _, cr: cairo.Context):
        self.get_style_ctx()

        cr.save()
        cr.translate(self.shift_offset_x, self.shift_offset_y)

        for i in range(len(self.segments)):
            self.draw_segment(cr, i, self.outer_radius, self.inner_radius)

        cr.restore()

    def draw_segment(
        self, cr: cairo.Context, index: int, outer_radius: float, inner_radius: float
    ):
        cr.save()

        segment = self.segments[index]
        state = segment.get_state_flags()

        cr.set_line_width(segment.get_border(state))
        cr.new_path()

        if segment.is_animating:
            p = segment.animated_padding
        else:
            p = segment.get_padding(state)

        inner_radius += p
        outer_radius -= p

        Gdk.cairo_set_source_rgba(
            cr, self.get_segment_style(index).get_property("background-color", state)
        )

        theta = (2 * math.pi) / len(self.segments)
        inner_theta = math.atan(p / (inner_radius)) if p != 0 else 0
        outer_theta = math.atan(p / (outer_radius)) if p != 0 else 0

        start_outer_angle = index * theta + outer_theta
        end_outer_angle = (index + 1) * theta - outer_theta

        start_inner_angle = index * theta + inner_theta
        end_inner_angle = (index + 1) * theta - inner_theta

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
            cr, self.get_segment_style(index).get_property("border-color", state)
        )

        cr.stroke()
        cr.restore()

    def animate_hover_in(self, index: int):
        segment = self.segments[index]
        animators = self.segment_animators[index]
        segment.is_animating = True
        animators["animating_type"] = "in"

        state = segment.get_state_flags()
        if not (state & Gtk.StateFlags.PRELIGHT):
            segment.set_state_flags(Gtk.StateFlags.PRELIGHT, False)

        normal_padding = segment.get_padding(Gtk.StateFlags.NORMAL)
        hover_padding = segment.get_padding(Gtk.StateFlags.PRELIGHT)

        animators["hover_out"].pause()

        animators["hover_in"].min_value = segment.animated_padding or normal_padding
        animators["hover_in"].max_value = hover_padding
        animators["hover_in"].play()

    def animate_hover_out(self, index: int):
        segment = self.segments[index]
        animators = self.segment_animators[index]
        animators["animating_type"] = "out"

        state = segment.get_state_flags()
        if state & Gtk.StateFlags.PRELIGHT:
            segment.unset_state_flags(Gtk.StateFlags.PRELIGHT)

        normal_padding = segment.get_padding(Gtk.StateFlags.NORMAL)

        animators["hover_in"].pause()

        animators["hover_out"].min_value = segment.animated_padding
        animators["hover_out"].max_value = normal_padding
        animators["hover_out"].play()

    def on_segment_animate(self, index: int, animator: Animator):
        segment = self.segments[index]
        segment.animated_padding = animator.value

        animators = self.segment_animators[index]
        if (
            animators["animating_type"] == "out"
            and animator == animators["hover_out"]
            and animator.value == animator.max_value
        ):
            segment.is_animating = False

        self.queue_draw()

    def animate_weight_shift(self, segment_index: int | None):
        self._shift_start_x = self.shift_offset_x
        self._shift_start_y = self.shift_offset_y

        if segment_index is None:
            self.target_shift_x = 0.0
            self.target_shift_y = 0.0
        else:
            angle_per_segment = (2 * math.pi) / len(self.segments)
            mid_angle = (segment_index + 0.5) * angle_per_segment

            self.target_shift_x = self.shift_distance * math.cos(mid_angle)
            self.target_shift_y = self.shift_distance * math.sin(mid_angle)

        # Reset and play animation
        self.shift_animator.pause()
        self.shift_animator.min_value = 0.0
        self.shift_animator.max_value = 1.0
        self.shift_animator.value = 0.0
        self.shift_animator.play()

    def on_shift_animate(self, animator: Animator, *_):
        progress = animator.value

        # Interpolate
        self.shift_offset_x = (
            self._shift_start_x + (self.target_shift_x - self._shift_start_x) * progress
        )
        self.shift_offset_y = (
            self._shift_start_y + (self.target_shift_y - self._shift_start_y) * progress
        )

        self.queue_draw()

    def on_motion(self, widget, event):
        segment = self.get_segment(event.x, event.y)
        if segment != self.hovered_segment:
            # Handle hover out for previous segment
            if self.hovered_segment is not None:
                self.previous_hovered = self.hovered_segment
                self.animate_hover_out(self.previous_hovered)

            # Handle hover in for new segment
            self.hovered_segment = segment
            if self.hovered_segment is not None:
                self.animate_hover_in(self.hovered_segment)
                self.animate_weight_shift(self.hovered_segment)
            else:
                self.animate_weight_shift(None)
                self.queue_draw()

    def on_click(self, _, event):
        if (segment := self.get_segment(event.x, y=event.y)) is not None:
            self.segments[segment].emit("clicked", True)
            self.queue_draw()

        self.set_state_flags(Gtk.StateFlags.PRELIGHT, False)

    def get_segment(self, x, y):
        dx, dy = x - self.center_x, y - self.center_y

        if (
            distance := math.sqrt(dx**2 + dy**2)
        ) > self.outer_radius or distance < self.inner_radius:
            return None

        if (angle := math.atan2(dy, dx)) < 0:
            angle += 2 * math.pi

        return int(angle / ((2 * math.pi) / len(self.segments)))

    def get_segment_style(self, index: int):
        return self.segments[index].get_style_context()


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
        self.segments = children
        self.center_child = center_child
        super().put(self.drawing_area, 0, 0)
        self.drawing_area.connect("size-allocate", self.on_size_allocate)

        self.drawing_area.connect("draw", self.on_drawing_area_draw)

    def on_size_allocate(self, _, __):
        self.move_widgets()

    def on_drawing_area_draw(self, *_):
        self.move_widgets()
        return False

    def move_widgets(self):
        shift_x = self.drawing_area.shift_offset_x
        shift_y = self.drawing_area.shift_offset_y

        for i in range(len(self.segments)):
            self.move_segment_child(i, shift_x, shift_y)
        if self.center_child is not None:
            child_size = self.center_child.get_preferred_size()
            center_x = self.drawing_area.center_x + shift_x
            center_y = self.drawing_area.center_y + shift_y

            if self.center_child in super().get_children():
                super().move(
                    self.center_child,
                    center_x - child_size.natural_size.width / 2,
                    center_y - child_size.natural_size.height / 2,
                )
                return
            super().put(
                self.center_child,
                center_x - child_size.natural_size.width / 2,
                center_y - child_size.natural_size.height / 2,
            )

    def move_segment_child(self, i: int, shift_x: float = 0, shift_y: float = 0):
        child = self.segments[i].child
        if child is None:
            return
        angle_step = (2 * math.pi) / len(self.segments)
        start_angle = i * angle_step
        end_angle = (i + 1) * angle_step

        child_size = child.get_preferred_size()
        segment_center_x, segment_center_y = polar_to_cartesian(
            self.drawing_area.center_x + shift_x,
            self.drawing_area.center_y + shift_y,
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
        style_classes="radial-segment",
        child=Box(
            orientation="vertical",
            children=[
                Image(
                    icon_name=[
                        "changes-prevent-symbolic",
                        "night-light-symbolic",
                        "system-reboot-symbolic",
                        "system-log-out-symbolic",
                        "system-shutdown-symbolic",
                    ][i],
                    icon_size=64,
                    style="color: black;",
                ),
                Label(
                    ["Lock", "Sleep", "Reboot", "Log Out", "Shut Down"][i],
                    style="color: black; font-size: 20px;",
                ),
            ],
        ),
    )
    for i in range(0, 5)
]


def on_child_click(child: RadialMenuSegment, _):
    print(f'Child with label "{child.child.get_children()[1].get_label()}" clicked!')


for child in radial_children:
    child.connect("clicked", on_child_click)


win = Window(
    layer="overlay",
    child=RadialMenu(
        name="radial-menu",
        children=radial_children,
        center_child=Box(
            orientation="v",
            name="radial-menu-center",
            children=[
                Image(
                    icon_name="emblem-system-symbolic",
                    icon_size=200,
                ),
                # Label("Power", style="color: black; font-size: 32px;"),
            ],
        ),
    ),
    anchor="center",
)

app = Application()
app.set_stylesheet_from_file("test_style.css")

app.run()
