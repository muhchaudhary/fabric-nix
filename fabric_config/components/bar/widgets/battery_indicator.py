import datetime
import math
from typing import Iterable, Literal

import cairo
import psutil
from fabric import Property
from fabric.core.fabricator import Fabricator
from fabric.utils import get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.widget import Widget
from gi.repository import Gdk, Gtk, Rsvg

from fabric_config.snippits.animator import Animator


class BatteryIndicator(Box):
    def __init__(self, **kwargs):
        super().__init__(v_align="center", h_align="start", **kwargs)
        if not psutil.sensors_battery():
            self.set_visible(False)
            return

        self.is_charging = None
        self.curr_percent = None
        self.battery_button = Button(name="panel-button")
        self.battery_body = BatteryBodyWidget(
            percentage=0,
            size=(50, 25),
            style="margin: 5px; background-color: green; border: solid white 2px; border-radius: 3px;",
        )

        self.current_class = ""
        self.battery_percent = Label(name="battery-label")

        self.battery_percent_revealer = Revealer(
            child=self.battery_percent,
            transition_type="slide-left",
        )

        self.battery = Fabricator(
            poll_from=self.poll_batt, interval=1000, on_changed=self.update_battery
        )
        self.battery_button.add(
            Box(
                children=[
                    self.battery_percent_revealer,
                    self.battery_body,
                ]
            )
        )

        self.battery_button.connect(
            "clicked",
            lambda *args: self.battery_percent_revealer.set_reveal_child(
                not self.battery_percent_revealer.get_child_revealed(),
            ),
        )

        self.add(self.battery_button)

    def update_battery(self, _, value):
        percent = value.percent
        secsleft = value.secsleft
        charging = value.power_plugged
        self.battery_percent.set_label(str(int(round(percent))) + "%")

        self.battery_button.set_tooltip_text(
            str(int(round(percent)))
            + "% "
            + str(datetime.timedelta(seconds=secsleft))
            + " left",
        ) if not charging else self.battery_button.set_tooltip_text(
            str(int(round(percent))) + "% " + "Charging",
        )

        if int(percent) != self.curr_percent:
            self.curr_percent = int(percent)
            self.battery_body.percentage = self.curr_percent

        if self.is_charging != charging:
            self.is_charging = charging
            if self.is_charging:
                self.battery_body.is_charging = True
            else:
                self.battery_body.is_charging = False

        if charging:
            if self.current_class != "charging":
                self.current_class = "charging"
                self.battery_percent.style_classes = [self.current_class]
        elif 30 < int(round(percent)) < 50:
            if self.current_class != "low":
                self.current_class = "low"
                self.battery_percent.style_classes = [self.current_class]

        elif int(round(percent)) <= 30:
            if self.current_class != "critical":
                self.current_class = "critical"
                self.battery_percent.style_classes = [self.current_class]
        elif self.current_class != "":
            self.current_class = ""
            self.battery_percent.style_classes = []

    def poll_batt(self):
        battery = psutil.sensors_battery()
        return battery if battery else None

    def on_click(self, *args):
        self.battery_percent_revealer.set_reveal_child(
            not self.battery_percent_revealer.get_child_revealed(),
        )


class BatteryBodyWidget(Gtk.DrawingArea, Widget):
    @Property(float, "read-write", default_value=0.0)
    def percentage(self) -> float:
        return self._percent

    @percentage.setter
    def percentage(self, value: float):
        self.queue_draw() if value != self._percent else None
        self._percent = value

    @Property(bool, "read-write", default_value=False)
    def is_charging(self) -> bool:
        return self._is_charging

    @is_charging.setter
    def is_charging(self, value: bool) -> bool:
        if self._is_charging != value:
            self._play_bolt_animation = True
            self.queue_draw()
        self._is_charging = value

    def __init__(
        self,
        percentage: float = 0.0,
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
        Gtk.DrawingArea.__init__(self)  # type: ignore
        self.bolt_svg: Rsvg.Handle = Rsvg.Handle.new_from_file(
            get_relative_path("../../../assets/bolt.svg")
        )  # type: ignore
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
        self._percent = percentage
        self._is_charging = False
        self._play_bolt_animation = False
        self._anim_is_running = False
        self._scale = 0.25
        self.connect("draw", self.on_draw)

    def run_bolt_animation(self):
        def on_new_value(p, *_):
            self._scale = p.value
            self.queue_draw()
            print("Playing....", p.value)

        def on_anim_finished(*_):
            self._anim_is_running = False

        anim = Animator(
            bezier_curve=(0, 0.77, 0.35, 1.67),
            duration=0.5,
            min_value=0.1,
            max_value=0.25,
            tick_widget=self,
            notify_value=on_new_value,
            on_finished=on_anim_finished,
        )
        anim.play()

    def draw_lightning_bolt(self, cr: cairo.Context, x, y, width, height):
        """Draw a lightning bolt centered at (center_x, center_y)."""
        # Calculate points for the lightning bolt
        center_x = x + width / 2
        center_y = y + height / 2
        cr.save()
        cr.translate(
            center_x - (self.bolt_svg.get_dimensions().width * self._scale) / 2 + 1,
            center_y - (self.bolt_svg.get_dimensions().height * self._scale) / 2,
        )
        cr.scale(self._scale, self._scale)
        self.bolt_svg.render_cairo(cr)
        cr.restore()

        # cr.move_to(center_x, center_y + bolt_height / 2) # Top
        # cr.line_to(center_x, center_y + bolt_height * 0.1) # Top-center
        # cr.line_to(center_x - bolt_width * 0.3, center_y + bolt_height * 0.1) # Mid-right
        # cr.line_to(center_x, center_y - bolt_height / 2) # Bottom
        # cr.line_to(center_x, center_y - bolt_height * 0.1) # Bottom-center
        # cr.line_to(center_x + bolt_width * 0.3, center_y - bolt_height * 0.1)  # Mid-left
        # cr.line_to(center_x, center_y + bolt_height / 2) # Top
        # cr.fill()

    def do_render_rectangle(self, cr: cairo.Context, width, height, radius: int = 0):
        cr.move_to(radius, 0)
        cr.line_to(width - radius, 0)
        cr.arc(width - radius, radius, radius, -(math.pi / 2), 0)
        cr.line_to(width, height - radius)
        cr.arc(width - radius, height - radius, radius, 0, (math.pi / 2))
        cr.line_to(radius, height)
        cr.arc(radius, height - radius, radius, (math.pi / 2), math.pi)
        cr.line_to(0, radius)
        cr.arc(radius, radius, radius, math.pi, (3 * (math.pi / 2)))
        cr.close_path()

    def on_draw(self, widget, cr: cairo.Context):
        style_context = self.get_style_context()
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()

        margin = style_context.get_margin(Gtk.StateFlags.NORMAL)
        background_color = style_context.get_background_color(Gtk.StateFlags.NORMAL)
        border = style_context.get_border(Gtk.StateFlags.BACKDROP)
        border_color = style_context.get_border_color(Gtk.StateFlags.NORMAL)
        border_radius = style_context.get_property(
            "border-radius", Gtk.StateFlags.NORMAL
        )

        fill_offset = 3
        terminal_width = 2

        margin = max(
            margin.left,
            margin.bottom,
            margin.right,
            margin.top,
        )

        border_width = max(
            border.top,  # type: ignore
            border.bottom,  # type: ignore
            border.left,  # type: ignore
            border.right,  # type: ignore
        )

        body_width = width - margin * 2 - terminal_width
        body_height = height - margin * 2
        terminal_height = body_height // 1.6

        cr.save()
        Gdk.cairo_set_source_rgba(cr, border_color)
        cr.set_line_width(border_width)
        cr.translate(margin, margin)
        self.do_render_rectangle(cr, body_width, body_height, border_radius)
        cr.stroke()
        cr.restore()

        # Draw battery terminal
        cr.save()
        Gdk.cairo_set_source_rgba(cr, border_color)

        terminal_x = margin + body_width + border_width / 2
        terminal_y = margin + (body_height - terminal_height) / 2

        cr.translate(terminal_x + border_width // 2, terminal_y)
        self.do_render_rectangle(cr, terminal_width, terminal_height, 2)
        cr.fill()
        cr.restore()

        # Fill battery level
        cr.save()
        fill_width = (self.percentage / 100) * body_width
        Gdk.cairo_set_source_rgba(cr, background_color)
        cr.translate(
            margin + (border_width + fill_offset) / 2,
            margin + (border_width + fill_offset) / 2,
        )
        self.do_render_rectangle(
            cr,
            fill_width - border_width - fill_offset,
            body_height - border_width - fill_offset,
            border_radius - border_width,
        )
        cr.fill()
        cr.restore()

        if self._play_bolt_animation:
            self.run_bolt_animation()
            self._play_bolt_animation = False
        elif self.is_charging:
            self.draw_lightning_bolt(cr, margin, margin, body_width, body_height)
