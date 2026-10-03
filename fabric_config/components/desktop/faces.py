"""The clock faces: digital, analog and word clock."""

import datetime
import math
from collections.abc import Callable

from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label
from gi.repository import Gdk, GLib, Gtk


class DigitalFace(EventBox):
    def __init__(
        self,
        on_click: Callable[[], None],
        on_menu: Callable[[Gdk.EventButton], None],
    ):
        self.time_label = Label(name="clock-time")
        super().__init__(
            events=["button-press"],
            child=self.time_label,
            h_align="center",
            style_classes=["clickable"],
            tooltip_text="Click to start a focus timer",
        )

        def on_press(_widget, event: Gdk.EventButton):
            if event.button == 1:
                on_click()
                return True
            if event.button == 3:
                on_menu(event)
                return True
            return False

        self.connect("button-press-event", on_press)

    def update(self, now: datetime.datetime, use_24h: bool):
        # like the macOS lock screen: no leading zero, no AM/PM
        hour = now.hour if use_24h else now.hour % 12 or 12
        self.time_label.set_label(f"{hour}:{now:%M}")

    def show_countdown(self, seconds: int):
        minutes, secs = divmod(max(0, seconds), 60)
        self.time_label.set_label(f"{minutes}:{secs:02}")


class AnalogFace(Gtk.DrawingArea):
    def __init__(self, size: int):
        super().__init__()
        self.set_size_request(size, size)
        self.set_halign(Gtk.Align.CENTER)
        self.get_style_context().add_class("clock-analog")
        self._now = datetime.datetime.now()
        self.connect("draw", self._on_draw)

    def update(self, now: datetime.datetime, _use_24h: bool):
        self._now = now
        self.queue_draw()

    def _on_draw(self, widget: Gtk.Widget, cr):
        color = widget.get_style_context().get_color(Gtk.StateFlags.NORMAL)
        w, h = widget.get_allocated_width(), widget.get_allocated_height()
        cx, cy, radius = w / 2, h / 2, min(w, h) / 2 - 6
        cr.set_line_cap(1)  # round
        ink = (color.red, color.green, color.blue)

        def stroke(width: float, alpha: float = 1.0):
            cr.set_source_rgba(*ink, alpha)
            cr.set_line_width(width)
            cr.stroke()

        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        stroke(1.5, 0.5)

        for i in range(12):
            angle = i * math.pi / 6
            major = i % 3 == 0
            inner = radius * (0.80 if major else 0.86)
            cr.move_to(cx + inner * math.sin(angle), cy - inner * math.cos(angle))
            cr.line_to(
                cx + radius * 0.92 * math.sin(angle),
                cy - radius * 0.92 * math.cos(angle),
            )
            stroke(5 if major else 2.5, 1 if major else 0.7)

        minute = self._now.minute
        hour = self._now.hour % 12 + minute / 60
        hands = (
            (hour * math.pi / 6, radius * 0.5, 9),
            (minute * math.pi / 30, radius * 0.76, 5),
        )
        for angle, length, width in hands:
            cr.move_to(cx, cy)
            cr.line_to(cx + length * math.sin(angle), cy - length * math.cos(angle))
            stroke(width)

        cr.arc(cx, cy, 7, 0, 2 * math.pi)
        cr.set_source_rgba(*ink, 1)
        cr.fill()
        return False


# (id, text) per row; ids distinguish the minute "FIVE"/"TEN" from the hours
_WORD_ROWS = [
    [("it", "IT"), ("is", "IS"), ("half", "HALF"), ("m10", "TEN")],
    [("quarter", "QUARTER"), ("twenty", "TWENTY")],
    [("m5", "FIVE"), ("minutes", "MINUTES"), ("to", "TO")],
    [("past", "PAST"), ("h1", "ONE"), ("h3", "THREE")],
    [("h2", "TWO"), ("h4", "FOUR"), ("h5", "FIVE")],
    [("h6", "SIX"), ("h7", "SEVEN"), ("h8", "EIGHT")],
    [("h9", "NINE"), ("h10", "TEN"), ("h11", "ELEVEN")],
    [("h12", "TWELVE"), ("oclock", "O'CLOCK")],
]
_MINUTE_WORDS = {
    0: ["oclock"],
    5: ["m5", "minutes", "past"],
    10: ["m10", "minutes", "past"],
    15: ["quarter", "past"],
    20: ["twenty", "minutes", "past"],
    25: ["twenty", "m5", "minutes", "past"],
    30: ["half", "past"],
    35: ["twenty", "m5", "minutes", "to"],
    40: ["twenty", "minutes", "to"],
    45: ["quarter", "to"],
    50: ["m10", "minutes", "to"],
    55: ["m5", "minutes", "to"],
}
# reading order, for lighting words one by one
_WORD_ORDER = [word_id for row in _WORD_ROWS for word_id, _ in row]
SWEEP_STEP_MS = 120


def lit_words(now: datetime.datetime) -> set[str]:
    rounded = now.minute // 5 * 5
    hour = now.hour + (1 if rounded > 30 else 0)
    return {"it", "is", f"h{hour % 12 or 12}", *_MINUTE_WORDS[rounded]}


class WordFace(Box):
    def __init__(self):
        super().__init__(orientation="v", h_align="center", name="clock-words")
        self.words: dict[str, Label] = {}
        self._sweep_ids: list[int] = []
        for row in _WORD_ROWS:
            line = Box(h_align="center", spacing=14)
            for word_id, text in row:
                label = Label(text, style_classes=["clock-word"])
                self.words[word_id] = label
                line.add(label)
            self.add(line)

    def _cancel_sweep(self):
        context = GLib.MainContext.default()
        for source_id in self._sweep_ids:
            # skip timers that already fired; removing those warns
            if context.find_source_by_id(source_id) is not None:
                GLib.source_remove(source_id)
        self._sweep_ids = []

    def update(self, now: datetime.datetime, _use_24h: bool, sweep: bool = False):
        self._cancel_sweep()
        lit = lit_words(now)
        if not sweep:
            for word_id, label in self.words.items():
                if word_id in lit:
                    label.add_style_class("lit")
                else:
                    label.remove_style_class("lit")
            return

        # on the hour: run a light along every word, then settle on the time
        for label in self.words.values():
            label.remove_style_class("lit")

        def flash(word_id: str, keep: bool):
            label = self.words[word_id]
            label.add_style_class("lit")
            if not keep:
                self._sweep_ids.append(
                    GLib.timeout_add(
                        SWEEP_STEP_MS * 2, lambda: label.remove_style_class("lit")
                    )
                )
            return False

        for i, word_id in enumerate(_WORD_ORDER):
            self._sweep_ids.append(
                GLib.timeout_add(i * SWEEP_STEP_MS, flash, word_id, word_id in lit)
            )
