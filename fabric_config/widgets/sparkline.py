from collections.abc import Sequence

import cairo
from gi.repository import Gtk


class Sparkline(Gtk.DrawingArea):
    """
    A small filled line chart of recent values, drawn in the widget's CSS
    `color`. `maximum` fixes the scale (100 for percentages); without it the
    chart scales to its largest value (network rates).
    """

    def __init__(
        self,
        capacity: int = 60,
        maximum: float | None = 100.0,
        height: int = 36,
        name: str = "sparkline",
    ):
        super().__init__()
        self.set_name(name)
        self.set_size_request(-1, height)
        self.set_hexpand(True)
        self.capacity = capacity
        self.maximum = maximum
        self.values: list[float] = []
        self.connect("draw", self._on_draw)
        # plain GTK widgets start hidden, unlike fabric's
        self.show()

    def set_values(self, values: Sequence[float]):
        self.values = list(values)[-self.capacity :]
        self.queue_draw()

    def _on_draw(self, _widget, cr: cairo.Context):
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        if len(self.values) < 2 or width <= 0:
            return
        color = self.get_style_context().get_color(Gtk.StateFlags.NORMAL)
        top = self.maximum or max(max(self.values), 1.0)
        step = width / (self.capacity - 1)
        # newest at the right edge; a short history starts partway in
        x0 = width - step * (len(self.values) - 1)
        inset = 1.5  # keep the stroke inside the widget

        def y(value: float) -> float:
            ratio = min(max(value / top, 0.0), 1.0)
            return height - inset - ratio * (height - 2 * inset)

        cr.move_to(x0, y(self.values[0]))
        for i, value in enumerate(self.values[1:], 1):
            cr.line_to(x0 + i * step, y(value))
        line = cr.copy_path()

        # soft fill fading down to nothing
        cr.line_to(width, height)
        cr.line_to(x0, height)
        cr.close_path()
        gradient = cairo.LinearGradient(0, 0, 0, height)
        gradient.add_color_stop_rgba(0, color.red, color.green, color.blue, 0.35)
        gradient.add_color_stop_rgba(1, color.red, color.green, color.blue, 0.0)
        cr.set_source(gradient)
        cr.fill()

        cr.append_path(line)
        cr.set_source_rgba(color.red, color.green, color.blue, 0.95)
        cr.set_line_width(1.5)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.stroke()
