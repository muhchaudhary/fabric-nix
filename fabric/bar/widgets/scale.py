import gi
from typing import Literal
from fabric.widgets.widget import Widget

gi.require_version("Gtk","3.0")
from gi.repository import Gtk

class Scale(Gtk.Scale, Widget):
    def __init__(
        self,
        min: float | None = 0,
        max: float | None = 1,
        step: float | None = 0.01,
        marks: int | None = None,
        mark_text: str | None = "x",
        digits: int | None = None,
        draw_value: bool | None = False,
        has_origin: bool | None = True, 
        value_pos: Literal[
            "bottom",
            "left",
            "right",
            "top",
        ]
        | Gtk.PositionType = None,
        mark_pos: Literal [
            "bottom",
            "left",
            "right",
            "top",            
        ] 
        | Gtk.PositionType = None,
        orientation: Literal[
            "horizontal",
            "vertical",
            "h",
            "v",
        ]
        | Gtk.Orientation = None,
        visible: bool = True,
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
        _orientation = (
            orientation
            if isinstance(orientation, Gtk.Orientation)
            else {
                "horizontal": Gtk.Orientation.HORIZONTAL,
                "vertical": Gtk.Orientation.VERTICAL,
                "h": Gtk.Orientation.HORIZONTAL,
                "v": Gtk.Orientation.VERTICAL,
            }.get(orientation, Gtk.Orientation.HORIZONTAL)
        )
        _value_pos = (
            value_pos
            if isinstance(orientation, Gtk.PositionType)
            else {
                "bottom": Gtk.PositionType.BOTTOM,
                "left": Gtk.PositionType.LEFT,
                "right": Gtk.PositionType.RIGHT,
                "top": Gtk.PositionType.TOP,
            }.get(value_pos, Gtk.PositionType.BOTTOM)
        )
        _mark_pos = (
            mark_pos
            if isinstance(orientation, Gtk.PositionType)
            else {
                "bottom": Gtk.PositionType.BOTTOM,
                "left": Gtk.PositionType.LEFT,
                "right": Gtk.PositionType.RIGHT,
                "top": Gtk.PositionType.TOP,
            }.get(mark_pos, Gtk.PositionType.BOTTOM)
        )
        Gtk.Scale.__init__(
            self,
            value_pos=_value_pos,
            orientation=_orientation,
            **kwargs,
        )
        super().set_digits(digits) if digits is not None else None
        super().set_draw_value(draw_value) if draw_value is not None else None
        super().set_has_origin(has_origin) if has_origin is not None else None
        super().set_range(min, max) if min is not None and max is not None else None
        super().set_increments(step,step) if step is not None else None
        super().add_mark(marks,_mark_pos,mark_text) if marks is not None else None
        

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
    def set_range(self,min,max):
        super().set_range(min,max)
