import gi
import math
import cairo
from typing import Literal, Iterable
from fabric.widgets.widget import Widget
from fabric.utils import get_gdk_rgba

gi.require_version("Gtk","3.0")
from gi.repository import Gdk, Gtk


# class Range(Gtk.Range, Widget):
#     def __init__(
#         self,
#         adjustment: Gtk.Adjustment = None,
#         fill_level: float | None = None,
#         inverted: bool | None = False,
#         restrict_to_fill_level: bool | None = True,
#         round_digits: int | None = None,
#         size_fixed: bool | None = False,
#         show_fill_level: bool | None = True,
#         can_focus: bool | None = True,
#         can_target: bool | None = True,
#         focus_on_click: bool | None = True,
#         focusable: bool | None  = True,
#         orientation: Literal[
#         "horizontal",
#         "vertical",
#         "h",
#         "v",
#         ] | Gtk.Orientation = None,
#         visible: bool | None = True,
#         all_visible: bool = False,
#         style: str | None = None,
#         style_compiled: bool = True,
#         style_append: bool = False,
#         style_add_brackets: bool = True,
#         tooltip_text: str | None = None,
#         tooltip_markup: str | None = None,
#         h_align: Literal["fill", "start", "end", "center", "baseline"]
#         | Gtk.Align
#         | None = None,
#         v_align: Literal["fill", "start", "end", "center", "baseline"]
#         | Gtk.Align
#         | None = None,
#         h_expand: bool = False,
#         v_expand: bool = False,
#         name: str | None = None,
#         size: tuple[int] | None = None,
#         **kwargs,
#     ):
#         """
#         do later
#         """
#         Gtk.Range.__init__(self, **kwargs)
#         super().set_adjustment(adjustment) if adjustment is not None else None
#         super().set_fill_level(fill_level) if fill_level is not None else None
#         super().set_inverted(inverted) if inverted is not None else None
#         super().set_range(min,max) if min is not None and max is not None else None
#         super().set_restrict_to_fill_level(restrict_to_fill_level) if restrict_to_fill_level is not None else None
#         super().set_round_digits(round_digits) if round_digits is not None else None
#         super().set_show_fill_level(show_fill_level) if show_fill_level is not None else None
#         super().set_slider_size_fixed(size_fixed) if size_fixed is not None else None
#         Widget.__init__(
#             self,
#             visible,
#             all_visible,
#             style,
#             style_compiled,
#             style_append,
#             style_add_brackets,
#             tooltip_text,
#             tooltip_markup,
#             h_align,
#             v_align,
#             h_expand,
#             v_expand,
#             name,
#             size,
#         )


class Scale(Gtk.Scale, Widget):
    def __init__(
        self,
        adjustment: Gtk.Adjustment = None,
        min: float | None = None,
        max: float | None = None,
        step: float | None = None,
        digits: int | None = None,
        draw_value: bool | None = False,
        has_origin: bool | None = True, 
        orientation: Literal[
            "horizontal",
            "vertical",
            "h",
            "v",
        ]
        | Gtk.Orientation = None,
        visible: bool | None = True,
        all_visible: bool = False,
        style: str | None = None,
        style_compiled: bool = True,
        style_append: bool = False,
        style_add_brackets: bool = True,
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
        name: str | None = None,
        size: tuple[int] | None = None,
        **kwargs,
       
    ):
        """
        Nothing for now
        """
        Gtk.Scale.__init__(self, **kwargs)
        super().set_digits(digits) if digits is not None else None
        super().set_draw_value(draw_value) if draw_value is not None else None
        super().set_has_origin(has_origin) if has_origin is not None else None
        super().set_adjustment(adjustment) if adjustment is not None else None
        super().set_range(min, max) if min is not None and max is not None else None
        super().set_increments(step,step) if step is not None else None

        # Get back to this
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
            size,
        )