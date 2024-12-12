import math
import os
from typing import Any, Iterable, Literal


import cairo
from fabric import Property, Signal
from fabric.widgets.box import Box
from fabric.widgets.image import Image
from fabric.widgets.revealer import Revealer
from fabric.widgets.shapes import Corner
from fabric.widgets.wayland import WaylandWindow
from fabric.widgets.widget import Widget

import fabric_config.config as config
from fabric_config.utils.hyprland_monitor import HyprlandWithMonitors
from fabric_config.widgets import PopupWindow

# gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gdk, Gtk


# class PopupWindow(WaylandWindow):
#     def __init__(
#         self,
#         child: Widget | None = None,
#         transition_type: Literal[
#             "none",
#             "crossfade",
#             "slide-right",
#             "slide-left",
#             "slide-up",
#             "slide-down",
#         ] = "none",
#         transition_duration: int = 100,
#         visible: bool = False,
#         anchor: str = "top right",
#         keyboard_mode: Literal["none", "exclusive", "on-demand"] = "on-demand",
#         timeout: int = 1000,
#         decorations: str = "margin: 1px",
#         **kwargs,
#     ):
#         self.timeout = timeout
#         self.currtimeout = 0
#         self.popup_running = False

#         self.monitor_number: int | None = None
#         self.hyprland_monitor = HyprlandWithMonitors()
#         self.revealer = Revealer(
#             child=child,
#             transition_type=transition_type,
#             transition_duration=transition_duration,
#             visible=False,
#         )
#         self.visible = visible
#         super().__init__(
#             layer="overlay",
#             anchor=anchor,
#             all_visible=False,
#             visible=False,
#             exclusive=False,
#             child=Box(style=decorations, children=self.revealer),
#             keyboard_mode=keyboard_mode,
#             **kwargs,
#         )
#         self.set_can_focus(False)

#         self.revealer.connect(
#             "notify::child-revealed",
#             lambda revealer, is_reveal: revealer.hide()
#             if not revealer.get_child_revealed()
#             else None,
#         )

#         self.show()

#     def toggle_popup(self, monitor: bool = False):
#         if monitor:
#             curr_monitor = self.hyprland_monitor.get_current_gdk_monitor_id()
#             self.monitor = curr_monitor

#             if self.monitor_number != curr_monitor and self.visible:
#                 self.monitor_number Gtkible
#         self.revealer.set_reveal_child(self.visible)

#     def toggle_popup_offset(self, offset, toggle_width):
#         if not self.visible:
#             self.revealer.show()
#         self.visible = not self.visible
#         self.revealer.set_reveal_child(self.visible)
#         self.revealer.set_margin_start(
#             offset - (self.revealer.get_allocated_width() - toggle_width) / 2
#         )

#     def popup_timeout(self):
#         curr_monitor = self.hyprland_monitor.get_current_gdk_monitor_id()
#         self.monitor = curr_monitor

#         if not self.visible:
#             self.revealer.show()

#         if self.popup_running:
#             self.currtimeout = 0
#             return

#         self.visible = True
#         self.revealer.set_reveal_child(self.visible)
#         self.popup_running = True

#         def popup_func():
#             if self.currtimeout >= self.timeout:
#                 self.visible = False
#                 self.revealer.set_reveal_child(self.visible)
#                 self.currtimeout = 0
#                 self.popup_running = False
#                 return False
#             self.currtimeout += 500
#             return True

#         GLib.timeout_add(500, popup_func)


class ProgressBar(Box):
    def __init__(self, progress_ticks: int = 10):
        self.progress_filled_class = "filled"
        self.total_progress_ticks = progress_ticks
        self.visible_progress_ticks = progress_ticks
        self.tick_boxes = [
            Box(v_expand=True, h_expand=True) for _ in range(self.total_progress_ticks)
        ]
        super().__init__(
            name="osd-progress-bar",
            spacing=5,
            v_expand=True,
            h_expand=True,
            orientation="v",
            children=self.tick_boxes,
        )

    def set_tick_number(self, ticks: int):
        self.visible_progress_ticks = ticks
        for child in super().children:
            child.set_visible(True)
        for i in range(self.total_progress_ticks - ticks):
            super().children[i].set_visible(False)

    def set_progress_filled(self, percent: float):
        # TODO: rework this later, just to get it working, am sleepy frfr
        for child in super().children:
            child.remove_style_class(self.progress_filled_class)
        for tick in range(int(self.visible_progress_ticks * percent)):
            super().children[-(tick + 1)].add_style_class(self.progress_filled_class)


class CairoProgressBar(Gtk.DrawingArea, Widget):
    @Property(float, "read-write", default_value=0.0)
    def value_filled(self) -> float:  # type: ignore
        return self._value

    @value_filled.setter
    def value_filled(self, value: float) -> None:
        self.queue_draw() if value != self._value else None
        self._value = value

    @Property(int, "read-write")
    def tick_number(self):  # type: ignore
        return self._tick_number

    @tick_number.setter
    def tick_number(self, value: int):
        self.queue_draw() if value != self._tick_number else None
        self._tick_number = value

    def __init__(
        self,
        start_value: float = 0.0,
        tick_number: int = 10,
        spacing: int = 5,
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
        self._tick_number = tick_number
        self._spacing = spacing
        self._value = start_value
        self.connect("draw", self.on_draw)
        # style_context = self.get_style_context()

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
        print("DRAWING")
        style_context = self.get_style_context()

        width = style_context.get_property("min-width", Gtk.StateFlags.NORMAL)
        height = style_context.get_property("min-height", Gtk.StateFlags.NORMAL)

        width = max(width, self.get_allocated_width())
        height = max(height, self.get_allocated_height())

        self.set_size_request(width, height)

        margin = style_context.get_margin(Gtk.StateFlags.NORMAL)
        color: Gdk.RGBA = style_context.get_color(Gtk.StateFlags.NORMAL)
        background_color: Gdk.RGBA = style_context.get_property(
            "background-color", Gtk.StateFlags.NORMAL
        )  # type: ignore
        # border = style_context.get_border(Gtk.StateFlags.BACKDROP)
        # border_color = style_context.get_border_color(Gtk.StateFlags.NORMAL)

        border_radius: int = style_context.get_property(
            "border-radius", Gtk.StateFlags.NORMAL
        )  # type: ignore

        margin = max(
            margin.left,
            margin.bottom,
            margin.right,
            margin.top,
        )

        # border_width = max(
        #     border.top,  # type: ignore
        #     border.bottom,  # type: ignore
        #     border.left,  # type: ignore
        #     border.right,  # type: ignore
        # )

        tick_height = (height) / ((self._tick_number) / 4) - self._spacing
        tick_width = width - margin * 2

        cr.save()

        tick_fill_up_to = int(self._value * self._tick_number)

        cr.translate(margin, height)

        Gdk.cairo_set_source_rgba(cr, background_color)
        for i in range(self._tick_number):
            cr.translate(0, -(tick_height + self._spacing) / 4)
            if i == tick_fill_up_to:
                Gdk.cairo_set_source_rgba(cr, color)
            self.do_render_rectangle(
                cr,
                tick_width,
                tick_height // 4,
                border_radius,
            )
            cr.fill()
        print(min(tick_width, tick_height) // 4)
        cr.restore()


class SystemOSD(PopupWindow):
    def __init__(self, **kwargs):
        self.brightness = config.brightness
        self.vol = 0
        self.progress_bar = ProgressBar(progress_ticks=20)
        # self.cairo_progress_bar = CairoProgressBar(
        #     name="osd-cairo-bar",
        #     tick_number=20,
        #     h_expand=True,
        #     v_expand=True,
        # )
        self.overlay_fill_box = Box(name="osd-box")
        self.icon = Image()

        super().__init__(
            enable_inhibitor=False,
            transition_duration=150,
            anchor="center-right",
            transition_type="crossfade",
            keyboard_mode="none",
            decorations="margin: 1px 0px 1px 1px;",
            child=Box(
                orientation="v",
                h_align="end",
                children=[
                    Box(
                        name="osd-corner",
                        children=Corner(
                            h_align="end",
                            orientation="bottom-right",
                            size=50,
                        ),
                    ),
                    Box(
                        name="osd",
                        orientation="v",
                        spacing=10,
                        h_align="end",
                        children=[
                            self.progress_bar,
                            # self.cairo_progress_bar,
                            Box(name="osd-icon", children=self.icon),
                        ],
                    ),
                    Box(
                        name="osd-corner",
                        children=Corner(
                            h_align="end",
                            orientation="top-right",
                            size=50,
                        ),
                    ),
                ],
            ),
            **kwargs,
        )

    def update_label_audio(self, *args):
        icon_name = "-".join(str(config.audio.speaker.icon_name).split("-")[0:2])
        self.icon.set_from_icon_name(icon_name + "-symbolic", 42)
        self.progress_bar.set_progress_filled(round(config.audio.speaker.volume) / 100)

        # self.cairo_progress_bar.value_filled = round(config.audio.speaker.volume) / 100

    def update_label_brightness(self):
        self.icon.set_from_icon_name("display-brightness-symbolic", 42)
        self.progress_bar.set_progress_filled(
            self.brightness.screen_brightness / self.brightness.max_screen
        )

        # self.cairo_progress_bar.value_filled = (
        #     self.brightness.screen_brightness / self.brightness.max_screen
        # )

    def update_label_keyboard(self, *args):
        self.icon.set_from_icon_name("keyboard-brightness-symbolic", 42)
        self.progress_bar.set_progress_filled(
            self.brightness.keyboard_brightness / self.brightness.max_kbd
        )

        # self.cairo_progress_bar.value_filled = (
        #     self.brightness.keyboard_brightness / self.brightness.max_kbd
        # )

    def enable_popup(self, type: str):
        match type:
            case "sound":
                self.update_label_audio()
            case "brightness":
                self.update_label_brightness()
            case "kbd":
                self.update_label_keyboard()

        self.popup_timeout()
