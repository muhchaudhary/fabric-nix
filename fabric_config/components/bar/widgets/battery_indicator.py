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
from fabric.widgets.widget import Widget
from gi.repository import Gdk, Gtk, Rsvg, Pango

from fabric_config.snippits.animator import Animator


class BatteryIndicator(Box):
    def __init__(self, **kwargs):
        super().__init__(v_align="center", h_align="start", **kwargs)
        if not psutil.sensors_battery():
            self.set_visible(False)
            return

        self.is_charging = False
        self.curr_percent = 0
        self.battery_button = Button(name="panel-button")
        self.battery_body = BatteryBodyWidget(
            name="battery-cairo-icon", percentage=0, style_classes="default"
        )

        self.current_class = ""

        self.battery = Fabricator(
            poll_from=self.poll_batt, interval=1000, on_changed=self.update_battery
        )
        self.battery_button.add(
            Box(
                children=[
                    self.battery_body,
                ]
            )
        )

        self.add(self.battery_button)

    def update_battery(self, _, value):
        percent = value.percent
        secsleft = value.secsleft
        charging = value.power_plugged

        if int(percent) != self.curr_percent or self.is_charging != charging:
            self.update_battery_class(int(percent), charging)

        if int(percent) != self.curr_percent:
            self.curr_percent = int(percent)
            self.battery_body.percentage = int(self.curr_percent)

        self.battery_button.set_tooltip_text(
            str(round(self.curr_percent))
            + "% "
            + str(datetime.timedelta(seconds=secsleft))
            + " left",
        ) if not charging else self.battery_button.set_tooltip_text(
            str(round(self.curr_percent)) + "% " + "Charging",
        )

        self.is_charging = charging
        self.battery_body.is_charging = charging

    def poll_batt(self, _):
        battery = psutil.sensors_battery()
        return battery if battery else None

    def update_battery_class(self, percent, is_charging):
        if is_charging:
            self.current_class = "charging"
            self.battery_body.style_classes = [self.current_class]
            return

        match percent:
            case num if 30 < num <= 50:
                self.current_class = "low"
                self.battery_body.style_classes = [self.current_class]

            case num if num <= 30:
                self.current_class = "critical"
                self.battery_body.style_classes = [self.current_class]

            case _:
                self.current_class = ""
                self.battery_body.style_classes = ["default"]


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
    def is_charging(self, value: bool):
        if self._is_charging != value:
            self.run_bolt_animation(not value)
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
        self._draw_bolt = False
        self._scale = 0.25
        self.connect("draw", self.on_draw)
        style_context = self.get_style_context()
        self.set_size_request(
            style_context.get_property("min-width", Gtk.StateFlags.NORMAL),
            style_context.get_property("min-height", Gtk.StateFlags.NORMAL),
        )

    def run_bolt_animation(self, reverse: bool = False):
        def on_new_value(p, *_):
            self._scale = p.value
            self.queue_draw()

        def on_anim_finished(*_):
            self._draw_bolt = not reverse

        min_value = 0.0
        max_value = 0.25

        anim = Animator(
            bezier_curve=(0, 0.77, 0.35, 1.67) if not reverse else (0, 0, 0.58, 1),
            duration=0.2,
            min_value=min_value if not reverse else max_value,
            max_value=max_value if not reverse else min_value,
            tick_widget=self,
            notify_value=on_new_value,
            on_finished=on_anim_finished,
        )
        self._draw_bolt = True
        anim.play()

    def draw_lightning_bolt(self, cr: cairo.Context, x, y, width, height):
        """Draw a lightning bolt centered at (center_x, center_y)."""
        # Calculate points for the lightning bolt
        center_x = x + width / 2
        center_y = y + height / 2
        cr.save()
        cr.translate(
            center_x - (self.bolt_svg.get_dimensions().width * self._scale) / 2,
            center_y - (self.bolt_svg.get_dimensions().height * self._scale) / 2,
        )
        cr.scale(self._scale, self._scale)
        self.bolt_svg.render_cairo(cr)
        cr.restore()

    def do_draw_battery_percent(
        self,
        cr: cairo.Context,
        x,
        y,
        width,
        height,
        color: Gdk.RGBA,
        font: Pango.FontDescription,
    ):
        center_x = x + width / 2
        center_y = y + height / 2

        cr.save()

        cr.set_font_size(min(height * 0.9, font.get_size()))

        cr.select_font_face(
            font.get_family(), cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD
        )
        extent = cr.text_extents(f"{int(self.percentage)}")
        cr.move_to(center_x - extent.width / 2, center_y + extent.height / 2)

        cr.text_path(f"{int(self.percentage)}")

        Gdk.cairo_set_source_rgba(cr, color)

        cr.fill_preserve()
        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(0.1)
        cr.stroke()
        cr.restore()

        pass

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

        width = style_context.get_property("min-width", Gtk.StateFlags.NORMAL)
        height = style_context.get_property("min-height", Gtk.StateFlags.NORMAL)
        self.set_size_request(width, height)

        margin = style_context.get_margin(Gtk.StateFlags.NORMAL)
        color: Gdk.RGBA = style_context.get_color(Gtk.StateFlags.NORMAL)
        background_color = style_context.get_property(
            "background-color", Gtk.StateFlags.NORMAL
        )
        border = style_context.get_border(Gtk.StateFlags.BACKDROP)
        border_color = style_context.get_border_color(Gtk.StateFlags.NORMAL)
        border_radius: int = style_context.get_property(
            "border-radius", Gtk.StateFlags.NORMAL
        )  # type: ignore

        font = style_context.get_font(Gtk.StateFlags.NORMAL)

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

        cr.translate(terminal_x + border_width / 2, terminal_y)
        self.do_render_rectangle(cr, terminal_width, terminal_height, 2)
        cr.fill()
        cr.restore()

        # Fill battery level
        cr.save()
        fill_width = (self.percentage / 100) * (body_width - border_width - fill_offset)
        Gdk.cairo_set_source_rgba(cr, background_color)
        # Gdk.cairo_set_source_rgba(cr, color)
        cr.translate(
            margin + (border_width + fill_offset) / 2,
            margin + (border_width + fill_offset) / 2,
        )
        self.do_render_rectangle(
            cr,
            fill_width,
            body_height - border_width - fill_offset,
            max(border_radius - border_width, 0),
        )
        cr.fill()
        cr.restore()

        if self._draw_bolt:
            self.draw_lightning_bolt(cr, margin, margin, body_width, body_height)
        else:
            self.do_draw_battery_percent(
                cr, margin, margin, body_width, body_height, color, font
            )
