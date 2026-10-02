"""
A seek bar for one MPRIS player, drawn as a row of level bars that move with
the music (cava): solid up to the playhead, faint after it, flat when
paused. Click or drag to scrub (it seeks when you let go); hovering shows a
ghost playhead with the time it would jump to.

It keeps its own position estimate, since players don't announce their
position: read when the track, status or a seek changes, counted forward
while playing.
"""

import math

import cairo
import gi
from gi.repository import Gdk, GLib, Gtk

import fabric_config.config as config
from fabric_config.services.mpris_v2 import MprisPlayer

gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

FRAME_MS = 33
BAR_W = 3
BAR_GAP = 2.4
BAR_MAX = 7.5  # half-height of the tallest level bar
HOVER_S = 0.15


def format_time(microseconds: float) -> str:
    seconds = max(0, int(microseconds // 1_000_000))
    return f"{seconds // 60}:{seconds % 60:02}"


class LevelSeekBar(Gtk.DrawingArea):
    def __init__(self, player: MprisPlayer, height: int = 40):
        super().__init__()
        self.set_name("level-seek-bar")
        self.set_size_request(-1, height)
        self.set_hexpand(True)
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        self.player = player
        self.cava = config.cava
        self._owner = f"seek-bar-{id(self)}"
        # a colour for the played part (e.g. from the album art); the
        # widget's CSS colour otherwise
        self.ink: tuple[float, float, float] | None = None

        self._levels: list[float] = []
        self._scrub: float | None = None
        self._hover = False
        self._hover_x = 0.0
        self._hover_amount = 0.0
        self._tick_id: int | None = None
        self._last_tick: float | None = None
        self._mapped = False

        # position estimate
        self._status = player.playback_status
        self._title = player.title
        self._pos_base = 0.0
        self._pos_time = GLib.get_monotonic_time() / 1e6

        self.connect("draw", self._on_draw)
        self.connect("map", lambda *_: self._set_mapped(True))
        self.connect("unmap", lambda *_: self._set_mapped(False))
        self.connect("destroy", lambda *_: self._set_mapped(False))
        self.connect("button-press-event", self._on_press)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("button-release-event", self._on_release)
        self.connect("leave-notify-event", self._on_leave)
        self._handlers = [
            player.connect("changed", lambda *_: self._on_player_changed()),
            player.connect("seeked", lambda *_: self._resync()),
        ]
        self.connect(
            "destroy", lambda *_: [player.disconnect(h) for h in self._handlers]
        )
        self._resync()
        GLib.timeout_add_seconds(1, self._second)

    # Position

    @property
    def length(self) -> int:
        return self.player.length or 0

    @property
    def position(self) -> float:
        """Estimated position in microseconds."""
        if self._status != "Playing":
            return self._pos_base
        elapsed = GLib.get_monotonic_time() / 1e6 - self._pos_time
        position = self._pos_base + elapsed * 1_000_000
        return min(position, self.length) if self.length else position

    @property
    def progress(self) -> float:
        if self._scrub is not None:
            return self._scrub
        return min(1.0, self.position / self.length) if self.length else 0.0

    def _resync(self):
        title = self.player.title

        def done(position: int):
            if title == self.player.title:
                self._pos_base = float(position)
                self._pos_time = GLib.get_monotonic_time() / 1e6
                self.queue_draw()

        self.player.fetch_position(done)

    def _on_player_changed(self):
        status, title = self.player.playback_status, self.player.title
        if status != self._status or title != self._title:
            reached = 0.0 if title != self._title else self.position
            self._status, self._title = status, title
            self._pos_base, self._pos_time = reached, GLib.get_monotonic_time() / 1e6
            self._resync()
            self._update_wanted()
            self._ensure_tick()
        self.queue_draw()

    def seek(self, fraction: float):
        if not self.length or not self.player.can_seek:
            return
        target = int(max(0.0, min(1.0, fraction)) * self.length)
        before = self.position
        self._pos_base, self._pos_time = float(target), GLib.get_monotonic_time() / 1e6
        if self.player.metadata.get("mpris:trackid"):
            self.player.seek_to(target)
        else:
            # SetPosition needs the track id; without one, seek relatively
            self.player.seek(target - int(before))
        self.queue_draw()

    # Levels and animation

    def _set_mapped(self, mapped: bool):
        self._mapped = mapped
        self._update_wanted()
        self._ensure_tick()

    def _update_wanted(self):
        self.cava.set_wanted(self._owner, self._mapped and self._status == "Playing")

    def _live(self) -> bool:
        return self._status == "Playing" and self.cava.running

    def _animating(self) -> bool:
        target = 1.0 if self._hover else 0.0
        return (
            self._live()
            or any(level > 0.01 for level in self._levels)
            or abs(self._hover_amount - target) > 0.01
        )

    def _ensure_tick(self):
        if self._mapped and self._animating() and self._tick_id is None:
            self._last_tick = None
            self._tick_id = GLib.timeout_add(FRAME_MS, self._tick)

    def _tick(self):
        now = GLib.get_monotonic_time() / 1e6
        dt = min(0.1, now - self._last_tick) if self._last_tick else FRAME_MS / 1000
        self._last_tick = now
        source = self.cava.bars if self._live() else []
        count = len(self._levels)
        for i in range(count):
            if source:
                # resample cava's bars onto however many fit
                pos = i / max(1, count - 1) * (len(source) - 1)
                low = int(pos)
                high = min(low + 1, len(source) - 1)
                target = source[low] + (source[high] - source[low]) * (pos - low)
            else:
                target = 0.0
            level = self._levels[i]
            self._levels[i] = level + (target - level) * (
                0.55 if target > level else 0.12
            )
        target = 1.0 if self._hover else 0.0
        step = dt / HOVER_S
        self._hover_amount += max(-step, min(step, target - self._hover_amount))
        self.queue_draw()
        if not self._mapped or not self._animating():
            self._tick_id = None
            return False
        return True

    def _second(self):
        if self._mapped and self._status == "Playing" and self._tick_id is None:
            self.queue_draw()
        return True

    # Input

    def _fraction(self, x: float) -> float:
        width = self.get_allocated_width()
        return max(0.0, min(1.0, x / width)) if width else 0.0

    def _on_press(self, _widget, event: Gdk.EventButton):
        if event.button != 1 or not self.length:
            return False
        self._scrub = self._fraction(event.x)
        self.queue_draw()
        return True

    def _on_motion(self, _widget, event: Gdk.EventMotion):
        self._hover_x = event.x
        if self._scrub is not None:
            self._scrub = self._fraction(event.x)
        elif not self._hover and self.length:
            self._hover = True
            window = self.get_window()
            if window is not None:
                window.set_cursor(
                    Gdk.Cursor.new_from_name(window.get_display(), "pointer")
                )
            self._ensure_tick()
        self.queue_draw()
        return False

    def _on_release(self, _widget, event: Gdk.EventButton):
        if self._scrub is None:
            return False
        self.seek(self._scrub)
        self._scrub = None
        self.queue_draw()
        return True

    def _on_leave(self, _widget, _event):
        if self._scrub is None:
            self._hover = False
            window = self.get_window()
            if window is not None:
                window.set_cursor(None)
            self._ensure_tick()
        return False

    # Drawing

    def _on_draw(self, widget: Gtk.Widget, cr: cairo.Context):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        style = widget.get_style_context().get_color(Gtk.StateFlags.NORMAL)
        text = (style.red, style.green, style.blue)
        ink = self.ink or text
        head = BAR_MAX + 3
        # bars in the lower part; the hover time bubble gets the top
        mid = height - head - 2

        count = max(8, int((width + BAR_GAP) / (BAR_W + BAR_GAP)))
        if len(self._levels) != count:
            self._levels = [0.0] * count
        step = (width - BAR_W) / (count - 1)
        played = width * self.progress
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(BAR_W)
        for i, level in enumerate(self._levels):
            x = BAR_W / 2 + i * step
            half = 1.2 + level * BAR_MAX
            cr.move_to(x, mid - half)
            cr.line_to(x, mid + half)
            if x <= played:
                cr.set_source_rgba(*ink, 0.95)
            else:
                cr.set_source_rgba(*text, 0.2)
            cr.stroke()

        # the playhead: a slim line a little taller than the bars
        cr.set_line_width(3.2 if self._scrub is not None else 2.2)
        cr.set_source_rgba(*text, 1)
        cr.move_to(played, mid - head)
        cr.line_to(played, mid + head)
        cr.stroke()

        glow = self._hover_amount * self._hover_amount * (3 - 2 * self._hover_amount)
        if glow > 0.01 and self._scrub is None and self.length:
            # where a click would land, and when that is
            ghost = max(0.0, min(float(width), self._hover_x))
            cr.set_line_width(1.6)
            cr.set_source_rgba(*text, 0.45 * glow)
            cr.move_to(ghost, mid - head)
            cr.line_to(ghost, mid + head)
            cr.stroke()
            layout = PangoCairo.create_layout(cr)
            description = Pango.FontDescription.from_string("Inter, Roboto Medium")
            description.set_absolute_size(10 * Pango.SCALE)
            description.set_weight(Pango.Weight.SEMIBOLD)
            layout.set_font_description(description)
            layout.set_text(format_time(self._fraction(ghost) * self.length), -1)
            lw, lh = layout.get_pixel_size()
            bw, bh = lw + 10, lh + 2
            bx = max(0.0, min(width - bw, ghost - bw / 2))
            by = 0.0
            radius = bh / 2
            cr.new_sub_path()
            cr.arc(bx + bw - radius, by + radius, radius, -math.pi / 2, math.pi / 2)
            cr.arc(bx + radius, by + radius, radius, math.pi / 2, 3 * math.pi / 2)
            cr.close_path()
            cr.set_source_rgba(*text, 0.9 * glow)
            cr.fill()
            # dark text on a light bubble, or the other way round
            shade = 0.0 if sum(text) > 1.5 else 1.0
            cr.set_source_rgba(shade, shade, shade, glow)
            cr.move_to(bx + 5, by + 1)
            PangoCairo.show_layout(cr, layout)
        return False
