"""
A radial quick menu that opens around the pointer (action `toggle_radial_menu`;
bind it to a key or mouse button). Point at a slice and click, press its
number, or Escape / click outside to close.

One transparent full-screen overlay on the focused monitor; the ring is drawn
with cairo in the colours of its CSS node (#radial-menu: `color`,
`background-color`, `border-color`) and the theme's @accent.
"""

import json
import math
from collections.abc import Callable
from dataclasses import dataclass

import cairo
import gi
from fabric.widgets.wayland import WaylandWindow
from loguru import logger

from fabric_config.utils.hyprland_monitor import get_hyprland_monitors

gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, GtkLayerShell  # noqa: E402

INNER = 48
OUTER = 138
ICON = 24
GAP = 0.035  # radians between slices
OPEN_MS = 160


@dataclass
class RadialItem:
    label: str
    icon_name: str
    action: Callable[[], object]


class RadialMenu(WaylandWindow):
    def __init__(self, items: list[RadialItem]):
        self.items = items
        self.area = Gtk.DrawingArea()
        self.area.set_name("radial-menu")
        self.area.add_events(
            Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.BUTTON_PRESS_MASK
        )
        self.area.connect("draw", self._on_draw)
        self.area.connect("motion-notify-event", self._on_motion)
        self.area.connect("button-press-event", self._on_press)
        self.area.show()
        super().__init__(
            title="fabric-radial",
            layer="overlay",
            anchor="top bottom left right",
            keyboard_mode="exclusive",
            visible=False,
            child=self.area,
        )
        # cover the whole monitor, bar included, so pointer coordinates
        # (from the monitor's corner) line up with ours
        GtkLayerShell.set_exclusive_zone(self, -1)
        self.connect("key-press-event", self._on_key)
        self.center = (0.0, 0.0)
        self.hovered: int | None = None
        self._progress = 0.0
        self._opened_at = 0
        self._tick: int | None = None
        self._icons: dict[str, GdkPixbuf.Pixbuf | None] = {}

    # Opening

    def toggle(self):
        if self.get_visible():
            self.close()
        else:
            self.open()

    def open(self):
        monitors = get_hyprland_monitors()
        self.monitor = monitors.get_current_gdk_monitor_id()
        self.center = _pointer_on_focused_monitor()
        self.hovered = None
        self._progress = 0.0
        self._opened_at = GLib.get_monotonic_time()
        self.show()
        if self._tick is None:
            self._tick = self.area.add_tick_callback(self._animate)

    def close(self):
        self.hide()
        if self._tick is not None:
            self.area.remove_tick_callback(self._tick)
            self._tick = None

    def _animate(self, _widget, clock: Gdk.FrameClock) -> bool:
        t = (clock.get_frame_time() - self._opened_at) / 1000 / OPEN_MS
        self._progress = min(1.0, max(0.0, t))
        self.area.queue_draw()
        if self._progress >= 1:
            self._tick = None
            return False
        return True

    def _activate(self, index: int):
        item = self.items[index]
        self.close()
        # let the overlay unmap first: screenshots and pickers shouldn't see it
        GLib.timeout_add(120, lambda: _run(item) or False)

    # Geometry

    def _ring_center(self) -> tuple[float, float]:
        """The pointer, nudged so the whole ring stays on screen."""
        w, h = self.area.get_allocated_width(), self.area.get_allocated_height()
        margin = OUTER + 8
        x = min(max(self.center[0], margin), max(margin, w - margin))
        y = min(max(self.center[1], margin), max(margin, h - margin))
        return x, y

    def _slice_at(self, x: float, y: float) -> int | None:
        cx, cy = self._ring_center()
        dx, dy = x - cx, y - cy
        distance = math.hypot(dx, dy)
        if distance < INNER * 0.6 or distance > OUTER + 40:
            return None
        # slice 0 is centred at the top, going clockwise
        angle = (math.atan2(dy, dx) + math.pi / 2) % math.tau
        step = math.tau / len(self.items)
        return int(((angle + step / 2) % math.tau) // step)

    # Input

    def _on_motion(self, _widget, event: Gdk.EventMotion):
        hovered = self._slice_at(event.x, event.y)
        if hovered != self.hovered:
            self.hovered = hovered
            self.area.queue_draw()
        return True

    def _on_press(self, _widget, event: Gdk.EventButton):
        index = self._slice_at(event.x, event.y)
        if event.button == 1 and index is not None:
            self._activate(index)
        else:
            self.close()
        return True

    def _on_key(self, _widget, event: Gdk.EventKey):
        if event.keyval == Gdk.KEY_Escape:
            self.close()
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.hovered is not None:
                self._activate(self.hovered)
            return True
        char = chr(Gdk.keyval_to_unicode(event.keyval) or 0)
        if char.isdigit() and 1 <= int(char) <= len(self.items):
            self._activate(int(char) - 1)
            return True
        # arrows walk round the ring
        step = {Gdk.KEY_Right: 1, Gdk.KEY_Down: 1, Gdk.KEY_Left: -1, Gdk.KEY_Up: -1}
        if event.keyval in step:
            current = self.hovered if self.hovered is not None else -step[event.keyval]
            self.hovered = (current + step[event.keyval]) % len(self.items)
            self.area.queue_draw()
            return True
        return False

    # Drawing

    def _icon(self, name: str, color: Gdk.RGBA) -> GdkPixbuf.Pixbuf | None:
        key = f"{name}:{color.to_string()}"
        if key not in self._icons:
            pixbuf = None
            info = Gtk.IconTheme.get_default().lookup_icon(
                name, ICON, Gtk.IconLookupFlags.FORCE_SIZE
            )
            if info is not None:
                try:
                    pixbuf, _ = info.load_symbolic(color, None, None, None)
                except GLib.Error:
                    pixbuf = None
            self._icons[key] = pixbuf
        return self._icons[key]

    def _on_draw(self, _widget, cr: cairo.Context):
        style = self.area.get_style_context()
        fg = style.get_color(Gtk.StateFlags.NORMAL)
        bg = style.get_property("background-color", Gtk.StateFlags.NORMAL)
        edge = style.get_property("border-color", Gtk.StateFlags.NORMAL)
        found, accent = style.lookup_color("accent")
        if not found:
            accent = fg
        on_accent = Gdk.RGBA(0.05, 0.05, 0.07, 1.0)

        # ease out, with a little overshoot
        p = self._progress
        ease = 1 - (1 - p) ** 3
        scale = 0.85 + 0.15 * ease + 0.04 * math.sin(p * math.pi)
        cx, cy = self._ring_center()
        cr.translate(cx, cy)
        cr.scale(scale, scale)
        alpha = ease

        count = len(self.items)
        step = math.tau / count
        for i, item in enumerate(self.items):
            start = -math.pi / 2 + i * step - step / 2 + GAP
            end = start + step - 2 * GAP
            hovered = i == self.hovered
            outer = OUTER + (6 if hovered else 0)

            cr.new_path()
            cr.arc(0, 0, outer, start, end)
            cr.arc_negative(0, 0, INNER, end, start)
            cr.close_path()
            fill = accent if hovered else bg
            cr.set_source_rgba(fill.red, fill.green, fill.blue, fill.alpha * alpha)
            cr.fill_preserve()
            cr.set_source_rgba(edge.red, edge.green, edge.blue, edge.alpha * alpha)
            cr.set_line_width(1)
            cr.stroke()

            middle = (start + end) / 2
            radius = (INNER + outer) / 2
            ix, iy = radius * math.cos(middle), radius * math.sin(middle)
            icon = self._icon(item.icon_name, on_accent if hovered else fg)
            if icon is not None:
                cr.save()
                cr.push_group()
                Gdk.cairo_set_source_pixbuf(cr, icon, ix - ICON / 2, iy - ICON / 2)
                cr.paint()
                cr.pop_group_to_source()
                cr.paint_with_alpha(alpha)
                cr.restore()

        # centre: what the hovered slice does
        cr.new_path()
        cr.arc(0, 0, INNER - 6, 0, math.tau)
        cr.set_source_rgba(bg.red, bg.green, bg.blue, min(1.0, bg.alpha + 0.25) * alpha)
        cr.fill()
        if self.hovered is not None:
            text = self.items[self.hovered].label
            cr.select_font_face(
                "Inter", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD
            )
            cr.set_font_size(11.5)
            extents = cr.text_extents(text)
            if extents.width > (INNER - 10) * 2:
                cr.set_font_size(11.5 * (INNER - 10) * 2 / extents.width)
                extents = cr.text_extents(text)
            cr.move_to(
                -extents.width / 2 - extents.x_bearing,
                -extents.height / 2 - extents.y_bearing,
            )
            cr.set_source_rgba(fg.red, fg.green, fg.blue, alpha)
            cr.show_text(text)


def _pointer_on_focused_monitor() -> tuple[float, float]:
    """The pointer, relative to the focused monitor's top-left corner."""
    connection = get_hyprland_monitors()
    try:
        cursor = json.loads(connection.send_command("j/cursorpos").reply)
        monitors = json.loads(connection.send_command("j/monitors").reply)
        monitor = next(m for m in monitors if m.get("focused"))
        return cursor["x"] - monitor["x"], cursor["y"] - monitor["y"]
    except Exception as e:
        logger.warning(f"[Radial] Couldn't find the pointer: {e}")
        return 0.0, 0.0


def _run(item: RadialItem):
    try:
        item.action()
    except Exception as e:
        logger.error(f"[Radial] {item.label} failed: {e}")
