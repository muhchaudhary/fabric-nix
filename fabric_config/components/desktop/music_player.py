"""
A simple music player card for the desktop, after the "Elegant Music
Player" Rainmeter skin: album art popping out of a rounded card, the title
and artist, a thin seek bar, and previous / play-pause / next. Synced lyrics
sit in a section underneath.

It follows the bar's theme (a white card in light mode, dark in dark mode,
the wallpaper accent for the current lyric) and lives in a window of its
own, so clicks and drags never compete with the rest of the desktop.
"""

import math
import os
import threading
import urllib.request
from collections.abc import Callable

import cairo
import gi
from fabric.widgets.wayland import WaylandWindow
from loguru import logger

from fabric_config.utils.uri import file_uri_to_path

gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango, PangoCairo  # noqa: E402

MEDIA_CACHE = os.path.join(GLib.get_user_cache_dir(), "fabric", "media")
FRAME_MS = 33
DRAG_THRESHOLD = 6
LYRIC_TRANSITION_S = 0.45
SEEK_BAR_W = 3  # px per level bar in the seek bar (at the 1440p reference)
SEEK_BAR_GAP = 2.4
HOVER_S = 0.15  # hover highlights ease in and out over this long
SEEK_BAR_MAX = 7.5  # half-height of the tallest level bar

# text: Pango, for real weights (cairo's toy text API only has regular/bold);
# the variable font lets a lyric's weight glide as it becomes current
FONT = "Inter Variable, Inter, Roboto"
LYRIC_WEIGHT_CURRENT = 500
LYRIC_WEIGHT_OTHER = 300
LYRIC_SIZE_CURRENT = 0.36  # of a line slot
LYRIC_SIZE_OTHER = 0.28


# Drawing helpers


def rounded_rect(cr: cairo.Context, x: float, y: float, w: float, h: float, r: float):
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


_shadow_cache: dict[tuple, tuple[cairo.ImageSurface, float]] = {}


def soft_shadow(
    cr: cairo.Context, x: float, y: float, w: float, h: float, r: float, depth: float
):
    """
    A blurred drop shadow (stacked, growing, faint rounded rects), drawn once
    per size into an image and painted from there afterwards.
    """
    key = (round(w), round(h), round(r), round(depth))
    cached = _shadow_cache.get(key)
    if cached is None:
        margin = depth
        surface = cairo.ImageSurface(
            cairo.FORMAT_ARGB32, int(w + margin * 2) + 2, int(h + margin * 2) + 2
        )
        _draw_shadow(cairo.Context(surface), margin, margin, w, h, r, depth)
        cached = (surface, margin)
        if len(_shadow_cache) > 16:
            _shadow_cache.clear()
        _shadow_cache[key] = cached
    surface, margin = cached
    cr.set_source_surface(surface, x - margin, y - margin)
    cr.paint()


def _draw_shadow(
    cr: cairo.Context, x: float, y: float, w: float, h: float, r: float, depth: float
):
    steps = 10
    for i in range(steps, 0, -1):
        spread = depth * i / steps
        rounded_rect(
            cr,
            x - spread / 2,
            y - spread / 2 + depth * 0.3,
            w + spread,
            h + spread,
            r + spread / 2,
        )
        # fainter toward the outside, so it fades rather than bands
        cr.set_source_rgba(0, 0, 0, 0.022 * (1 - i / (steps + 1)) + 0.006)
        cr.fill()


def text_layout(
    cr: cairo.Context,
    text: str,
    size: float,
    weight: float,
    width: float | None = None,
    align: Pango.Alignment = Pango.Alignment.LEFT,
    wrap: bool = False,
) -> Pango.Layout:
    layout = PangoCairo.create_layout(cr)
    description = Pango.FontDescription.from_string(FONT)
    description.set_absolute_size(size * Pango.SCALE)
    # the axis for variable fonts; static fallbacks get the nearest weight
    description.set_variations(f"wght={round(weight)}")
    description.set_weight(
        Pango.Weight.BOLD
        if weight >= 650
        else Pango.Weight.MEDIUM
        if weight >= 450
        else Pango.Weight.NORMAL
        if weight >= 350
        else Pango.Weight.LIGHT
    )
    layout.set_font_description(description)
    if width is not None:
        layout.set_width(int(width * Pango.SCALE))
        if wrap:
            layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        else:
            layout.set_ellipsize(Pango.EllipsizeMode.END)
    layout.set_alignment(align)
    layout.set_text(text, -1)
    return layout


def paint_pixbuf(
    cr: cairo.Context, pixbuf: GdkPixbuf.Pixbuf, x: float, y: float, size: float
):
    """Paint `pixbuf` cover-scaled into the square at (x, y)."""
    scale = size / min(pixbuf.get_width(), pixbuf.get_height())
    cr.save()
    cr.translate(x, y)
    cr.scale(scale, scale)
    Gdk.cairo_set_source_pixbuf(
        cr,
        pixbuf,
        (size / scale - pixbuf.get_width()) / 2,
        (size / scale - pixbuf.get_height()) / 2,
    )
    cr.paint()
    cr.restore()


def icon(cr: cairo.Context, kind: str, cx: float, cy: float, size: float):
    """Draw a media icon centred on (cx, cy) in the current source."""
    s = size / 2
    match kind:
        case "play":
            cr.move_to(cx - s * 0.55, cy - s)
            cr.line_to(cx + s * 0.95, cy)
            cr.line_to(cx - s * 0.55, cy + s)
            cr.close_path()
        case "pause":
            cr.rectangle(cx - s * 0.7, cy - s, s * 0.5, s * 2)
            cr.rectangle(cx + s * 0.2, cy - s, s * 0.5, s * 2)
        case "next" | "previous":
            d = 1 if kind == "next" else -1
            for shift in (-0.5, 0.5):
                tip = cx + d * s * (shift + 0.5)
                base = tip - d * s
                cr.move_to(base, cy - s * 0.7)
                cr.line_to(tip, cy)
                cr.line_to(base, cy + s * 0.7)
                cr.close_path()
    cr.fill()


def format_time(microseconds: float) -> str:
    seconds = max(0, int(microseconds // 1_000_000))
    return f"{seconds // 60:02}:{seconds % 60:02}"


def load_art(url: str | None, callback: Callable[[GdkPixbuf.Pixbuf | None], None]):
    """Load (downloading and caching remote art) off the main thread."""
    if not url:
        callback(None)
        return
    if url.startswith("file://"):
        path = file_uri_to_path(url)
    else:
        digest = GLib.compute_checksum_for_string(GLib.ChecksumType.SHA1, url, -1)
        path = os.path.join(MEDIA_CACHE, digest or "art")

    def work():
        pixbuf = None
        try:
            if not os.path.exists(path):
                os.makedirs(MEDIA_CACHE, exist_ok=True)
                urllib.request.urlretrieve(url, path)
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 400, 400, True)
        except Exception as e:
            logger.debug(f"[Music player] No art from {url}: {e}")
        GLib.idle_add(lambda: callback(pixbuf) or False)

    threading.Thread(target=work, daemon=True).start()


# The card


class MusicPlayer(Gtk.EventBox):
    def __init__(
        self,
        media,  # MediaState
        cava,  # Cava, for the seek bar's levels
        on_move_by: Callable[[int, int], None],
        on_moved: Callable[[], None],
        on_resize: Callable[[], None],
        on_toggle_lyrics: Callable[[], None],
    ):
        super().__init__()
        self.set_name("music-player")
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.SMOOTH_SCROLL_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        self.media = media
        self.cava = cava
        self._on_move_by = on_move_by
        self._on_moved = on_moved
        self._on_resize = on_resize
        self._on_toggle_lyrics = on_toggle_lyrics

        self.area = Gtk.DrawingArea()
        self.add(self.area)
        self.area.connect("draw", self._on_draw)
        self.connect("button-press-event", self._on_press)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("button-release-event", self._on_release)
        self.connect("scroll-event", self._on_scroll)
        self.connect("leave-notify-event", self._on_leave)

        self._set_sizes(1.0)

        # track state
        self.title = ""
        self.artist = ""
        self.status = "Stopped"
        self.length = 0
        self.source = ""
        self.source_count = 0
        self._art_url: str | None = None
        self.art_pixbuf: GdkPixbuf.Pixbuf | None = None

        # palette
        self.is_light = False
        self.accent = (0.75, 0.8, 0.95)
        self.show_lyrics = True

        # lyrics
        self._lyric_index = -1
        self._lyric_slide = 0.0  # 1 -> 0 as a new line takes over
        self._lyrics_poll: int | None = None
        self._has_lyrics_section = False

        # animation and input
        self.visible_on_desktop = True
        self._tick_id: int | None = None
        self._last_tick: float | None = None
        self._hits: list[tuple[str, tuple[float, float, float, float]]] = []
        self._press: tuple[float, float] | None = None
        self._dragged = 0.0
        self._dragging = False
        self._scrub: float | None = None  # fraction while dragging the seek bar
        self._seek_rect = (0.0, 0.0, 0.0, 0.0)
        self._levels: list[float] = []  # eased cava levels, one per seek bar
        self._layouts: dict[tuple, Pango.Layout] = {}
        # where the seek bar was last drawn: (x, width, centre y)
        self._seek_geometry: tuple[float, float, float] | None = None
        # hover: what's under the pointer, and each control's eased highlight
        self._hover: str | None = None
        self._hover_x = 0.0
        self._hover_amount: dict[str, float] = {}
        self._cursor_name: str | None = None

        self._layout()
        self._second_id: int | None = GLib.timeout_add_seconds(1, self._second)
        # monitor hotplug destroys the desktop's windows; a timer left running
        # keeps the old card alive, still drawing
        self.connect("destroy", lambda *_: self._stop_timers())

    # Layout

    def _set_sizes(self, scale: float):
        """
        Sizes in pixels at `scale`. The card is the same size on every
        screen (not shrunk on smaller ones); the scale is a per-display
        choice from the desktop menu.
        """
        u = scale
        self.card_w = round(560 * u)
        self.info_h = round(172 * u)
        self.art = round(200 * u)
        self.overflow = (self.art - self.info_h) // 2  # art above/below the card
        self.strip_w = round(52 * u)
        self.radius = round(16 * u)
        self.gap = round(26 * u)
        self.lyrics_h = round(132 * u)
        self.u = u

    def set_scale(self, scale: float):
        if abs(scale - self.u) < 1e-3:
            return
        self._set_sizes(scale)
        self._levels = []  # recomputed for the new width
        before = self.total_h
        self._layout()
        if self.total_h != before:
            self._on_resize()
        self.queue_draw()

    def _layout(self):
        """Size the card; the lyrics section only exists when there are lyrics."""
        self._has_lyrics_section = self.show_lyrics and bool(self.media.lyrics)
        self.card_top = self.overflow
        info_bottom = self.card_top + self.info_h
        if self._has_lyrics_section:
            self.lyrics_top = self.overflow + self.art + self.gap // 3
            self.card_bottom = self.lyrics_top + self.lyrics_h
            self.total_h = self.card_bottom + self.gap // 3
        else:
            self.lyrics_top = info_bottom
            self.card_bottom = info_bottom
            self.total_h = info_bottom + self.overflow
        self.area.set_size_request(self.card_w, self.total_h)

    @property
    def total_height(self) -> int:
        return self.total_h

    def _relayout(self):
        before = self.total_h
        self._layout()
        if self.total_h != before:
            self._on_resize()
        self.queue_draw()

    def set_palette(self, is_light: bool, accent: tuple[float, float, float] | None):
        self.is_light = is_light
        if accent is not None:
            self.accent = accent
        self.queue_draw()

    @property
    def ink(self) -> tuple[float, float, float]:
        return (0.11, 0.11, 0.13) if self.is_light else (0.95, 0.95, 0.97)

    @property
    def surface(self) -> tuple[float, float, float, float]:
        return (1, 1, 1, 0.97) if self.is_light else (0.12, 0.12, 0.14, 0.94)

    # State

    def update_track(self):
        player = self.media.current_player()
        self.source_count = len(self.media.players())
        if player is None:
            self.title, self.artist, self.status, self.length = "", "", "Stopped", 0
            self.source = ""
            self._set_art(None)
        else:
            self.title = player.title or ""
            self.artist = ", ".join(a for a in (player.artist or []) if a)
            self.status = player.playback_status
            self.length = player.length or 0
            self.source = player.player_name
            self._set_art(player.arturl)
        self._lyric_index = self.media.lyric_index()
        self._update_lyrics_poll()
        self._ensure_tick()
        self.queue_draw()

    def set_show_lyrics(self, show: bool):
        self.show_lyrics = show
        self.lyrics_changed()

    def lyrics_changed(self):
        self._lyric_index = self.media.lyric_index()
        self._update_lyrics_poll()
        self._relayout()

    def _set_art(self, url: str | None):
        if url == self._art_url:
            return
        self._art_url = url
        self.art_pixbuf = None

        def done(pixbuf):
            if url == self._art_url:
                self.art_pixbuf = pixbuf
                self.queue_draw()

        load_art(url, done)

    @property
    def position(self) -> float:
        return self.media.position

    @property
    def progress(self) -> float:
        if self._scrub is not None:
            return self._scrub
        return min(1.0, self.position / self.length) if self.length else 0.0

    # Lyrics timing

    def _update_lyrics_poll(self):
        wanted = (
            self._has_lyrics_section
            and self.status == "Playing"
            and self.visible_on_desktop
        )
        if wanted and self._lyrics_poll is None:
            self._lyrics_poll = GLib.timeout_add(200, self._poll_lyrics)
        elif not wanted and self._lyrics_poll is not None:
            GLib.source_remove(self._lyrics_poll)
            self._lyrics_poll = None

    def _poll_lyrics(self):
        index = self.media.lyric_index()
        if index != self._lyric_index:
            self._lyric_index = index
            self._lyric_slide = 1.0
            self._ensure_tick()
        return True

    # Animation: lyric slides, and the seek bar moving with the music

    def _levels_live(self) -> bool:
        return self.status == "Playing" and self.cava.running

    def _levels_settling(self) -> bool:
        return any(level > 0.01 for level in self._levels)

    def _hover_settling(self) -> bool:
        return any(
            abs((1.0 if name == self._hover else 0.0) - amount) > 0.01
            for name, amount in self._hover_amount.items()
        ) or (self._hover is not None and self._hover not in self._hover_amount)

    def _animating(self) -> bool:
        return (
            self._lyric_slide > 0
            or self._levels_live()
            or self._levels_settling()
            or self._hover_settling()
        )

    def _ensure_tick(self):
        wanted = self.visible_on_desktop and self._animating()
        if wanted and self._tick_id is None:
            self._last_tick = None
            self._tick_id = GLib.timeout_add(FRAME_MS, self._tick)

    def _tick(self):
        now = GLib.get_monotonic_time() / 1e6
        dt = min(0.1, now - self._last_tick) if self._last_tick else FRAME_MS / 1000
        self._last_tick = now
        sliding = self._lyric_slide > 0
        hovering = self._hover_settling() or self._hover == "seek"
        self._lyric_slide = max(0.0, self._lyric_slide - dt / LYRIC_TRANSITION_S)
        self._step_levels()
        self._step_hover(dt)
        area = self._seek_only_area()
        if sliding or hovering or area is None or self._scrub is not None:
            self.queue_draw()
        else:
            self.area.queue_draw_area(*area)
        if not self.visible_on_desktop or not self._animating():
            self._tick_id = None
            return False
        return True

    def _step_hover(self, dt: float):
        if self._hover is not None:
            self._hover_amount.setdefault(self._hover, 0.0)
        step = dt / HOVER_S
        for name in list(self._hover_amount):
            target = 1.0 if name == self._hover else 0.0
            amount = self._hover_amount[name]
            amount += max(-step, min(step, target - amount))
            if amount <= 0 and target == 0:
                del self._hover_amount[name]
            else:
                self._hover_amount[name] = amount

    def _hovered(self, name: str) -> float:
        """How highlighted `name` is right now, 0-1, eased."""
        t = self._hover_amount.get(name, 0.0)
        return t * t * (3 - 2 * t)

    def _step_levels(self):
        count = len(self._levels)
        if count == 0:
            return
        source = self.cava.bars if self._levels_live() else []
        for i in range(count):
            if source:
                # resample cava's bars onto however many fit in the seek bar
                pos = i / max(1, count - 1) * (len(source) - 1)
                low = int(pos)
                high = min(low + 1, len(source) - 1)
                target = source[low] + (source[high] - source[low]) * (pos - low)
            else:
                target = 0.0
            level = self._levels[i]
            # rise quickly, fall gently
            self._levels[i] = level + (target - level) * (
                0.55 if target > level else 0.12
            )

    def set_desktop_visible(self, visible: bool):
        self.visible_on_desktop = visible
        self._update_lyrics_poll()
        self._ensure_tick()

    def _stop_timers(self):
        for name in ("_second_id", "_lyrics_poll", "_tick_id"):
            if (source := getattr(self, name, None)) is not None:
                GLib.source_remove(source)
                setattr(self, name, None)

    def _second(self):
        # the seek bar and times move on their own
        if self.status == "Playing" and self.visible_on_desktop:
            self.queue_draw()
        return True

    # Input

    def _on_press(self, _widget, event: Gdk.EventButton):
        if event.button != 1:
            return False
        self._press = (event.x, event.y)
        self._dragged = 0.0
        self._dragging = False
        if self._in_seek_bar(event.x, event.y) and self.length:
            # pressing the seek bar scrubs rather than moving the window
            self._scrub = self._seek_fraction(event.x)
            self.queue_draw()
        return True

    def _in_seek_bar(self, x: float, y: float) -> bool:
        sx, sy, sw, sh = self._seek_rect
        return sx - 6 <= x <= sx + sw + 6 and sy <= y <= sy + sh

    def _seek_fraction(self, x: float) -> float:
        sx, _sy, sw, _sh = self._seek_rect
        return max(0.0, min(1.0, (x - sx) / sw)) if sw else 0.0

    def _set_cursor(self, name: str | None):
        if name == self._cursor_name:
            return
        self._cursor_name = name
        window = self.get_window()
        if window is None:
            return
        display = window.get_display()
        window.set_cursor(Gdk.Cursor.new_from_name(display, name) if name else None)

    def _hit_at(self, x: float, y: float) -> str | None:
        if self._in_seek_bar(x, y) and self.length:
            return "seek"
        for action, (hx, hy, hw, hh) in self._hits:
            if hx <= x <= hx + hw and hy <= y <= hy + hh:
                return action
        return None

    def _on_leave(self, _widget, event: Gdk.EventCrossing):
        # moving onto a child isn't leaving
        if event.detail == Gdk.NotifyType.INFERIOR or self._press is not None:
            return False
        self._hover = None
        self._set_cursor(None)
        self._ensure_tick()
        return False

    def _on_motion(self, _widget, event: Gdk.EventMotion):
        if self._press is None:
            hover = self._hit_at(event.x, event.y)
            self._hover_x = event.x
            if hover != self._hover:
                self._hover = hover
                self._set_cursor("pointer" if hover else None)
                self._ensure_tick()
            elif hover == "seek":
                self.queue_draw()  # the ghost playhead follows the pointer
            return False
        if self._scrub is not None:
            self._scrub = self._seek_fraction(event.x)
            self.queue_draw()
            return True
        dx, dy = event.x - self._press[0], event.y - self._press[1]
        self._dragged += math.hypot(dx, dy)
        if not self._dragging and self._dragged > DRAG_THRESHOLD:
            self._dragging = True
            self._hover = None
            self._set_cursor("grabbing")
        if self._dragging and (dx or dy):
            # the window moves under the pointer, so the press point stays
            # put in window coordinates (Wayland has no global position)
            self._on_move_by(round(dx), round(dy))
        return True

    def _on_release(self, _widget, event: Gdk.EventButton):
        if self._press is None:
            return False
        self._press = None
        if self._scrub is not None:
            self.media.seek(self._scrub)
            self._scrub = None
            self.queue_draw()
            return True
        if self._dragging:
            self._dragging = False
            self._set_cursor(None)
            self._on_moved()
            return True
        for action, (x, y, w, h) in self._hits:
            if x <= event.x <= x + w and y <= event.y <= y + h:
                self._act(action, (event.x - x) / w if w else 0)
                break
        return True

    def _on_scroll(self, _widget, event: Gdk.EventScroll):
        match event.direction:
            case Gdk.ScrollDirection.UP:
                step = -1
            case Gdk.ScrollDirection.DOWN:
                step = 1
            case Gdk.ScrollDirection.SMOOTH:
                step = 1 if event.delta_y > 0 else -1 if event.delta_y < 0 else 0
            case _:
                step = 0
        if step:
            self.media.cycle_player(step)
        return True

    def _act(self, action: str, fraction: float):
        match action:
            case "switch":
                self.media.cycle_player(1)
            case "lyrics":
                # saved as this display's "Lyrics" widget, like the menu
                self._on_toggle_lyrics()
            case _:
                self.media.act(action)

    # Drawing

    def _on_draw(self, _widget, cr: cairo.Context):
        area = self._seek_only_area()
        if area is not None:
            x1, y1, x2, y2 = cr.clip_extents()
            ax, ay, aw, ah = area
            if x1 >= ax and y1 >= ay and x2 <= ax + aw and y2 <= ay + ah:
                # a level-only frame: repaint the card behind the seek bar
                # and the bar itself, not the whole card
                rounded_rect(cr, 0, self.card_top, self.card_w,
                             self.card_bottom - self.card_top, self.radius)  # fmt: skip
                cr.set_source_rgba(*self.surface)
                cr.fill()
                self._draw_seek(cr)
                return False
        self._hits = []
        w = self.card_w
        top, bottom = self.card_top, self.card_bottom
        ink = self.ink
        u = self.u

        # card
        soft_shadow(cr, 0, top, w, bottom - top, self.radius, 18 * u)
        rounded_rect(cr, 0, top, w, bottom - top, self.radius)
        cr.set_source_rgba(*self.surface)
        cr.fill()

        # side strip: switch player, toggle lyrics
        cx = self.strip_w / 2
        mid = top + self.info_h / 2
        for name, icon_y in (
            ("switch", mid - self.info_h * 0.2),
            ("lyrics", mid + self.info_h * 0.2),
        ):
            if glow := self._hovered(name):
                size = 36 * u
                rounded_rect(cr, cx - size / 2, icon_y - size / 2, size, size, 10 * u)
                cr.set_source_rgba(*ink, 0.09 * glow)
                cr.fill()
        self._draw_switch_icon(cr, cx, mid - self.info_h * 0.2, 18 * u)
        self._hits.append(
            ("switch", (0, mid - self.info_h * 0.42, self.strip_w, self.info_h * 0.4))
        )
        self._draw_lyrics_icon(cr, cx, mid + self.info_h * 0.2, 18 * u)
        self._hits.append(("lyrics", (0, mid + 2, self.strip_w, self.info_h * 0.4)))

        # album art, popping out above and below
        ax, ay = self.strip_w, 0
        soft_shadow(cr, ax, ay, self.art, self.art, 6 * u, 14 * u)
        cr.save()
        rounded_rect(cr, ax, ay, self.art, self.art, 6 * u)
        cr.clip()
        if self.art_pixbuf is not None:
            paint_pixbuf(cr, self.art_pixbuf, ax, ay, self.art)
        else:
            gradient = cairo.LinearGradient(ax, ay, ax + self.art, ay + self.art)
            gradient.add_color_stop_rgb(0, *self.accent)
            gradient.add_color_stop_rgb(1, *(c * 0.45 for c in self.accent))
            cr.set_source(gradient)
            cr.paint()
            cr.set_source_rgba(1, 1, 1, 0.85)
            note = text_layout(cr, "♪", self.art * 0.4, 400)
            nw, nh = note.get_pixel_size()
            cr.move_to(ax + (self.art - nw) / 2, ay + (self.art - nh) / 2)
            PangoCairo.show_layout(cr, note)
        cr.restore()

        # title and artist
        tx = ax + self.art + self.gap
        tw = w - tx - self.gap
        y = top + self.info_h * 0.13
        title = self.title.upper() if self.title else "NOTHING PLAYING"
        cr.set_source_rgba(*ink, 1)
        layout = text_layout(cr, title, 21 * u, 700, tw)
        cr.move_to(tx, y)
        PangoCairo.show_layout(cr, layout)
        y += layout.get_pixel_size()[1] + 4 * u
        subtitle = self.artist or (
            self.source.capitalize() if self.source else "Play something"
        )
        if self.source_count > 1 and self.source:
            subtitle += f"  ·  {self.source.capitalize()}"
        cr.set_source_rgba(*ink, 0.7)
        layout = text_layout(cr, subtitle, 14 * u, 400, tw)
        cr.move_to(tx, y)
        PangoCairo.show_layout(cr, layout)

        # seek bar: a row of level bars that move with the music (cava)
        bar_y = top + self.info_h * 0.585
        self._seek_geometry = (tx, tw, bar_y)
        self._draw_seek(cr)

        # times
        cr.set_source_rgba(*ink, 0.75)
        for text, align, x in (
            (format_time(self.progress * self.length), Pango.Alignment.LEFT, tx),
            (
                format_time(self.length) if self.length else "--:--",
                Pango.Alignment.RIGHT,
                tx,
            ),
        ):
            layout = text_layout(cr, text, 11.5 * u, 450, tw, align)
            cr.move_to(x, bar_y + 14 * u)
            PangoCairo.show_layout(cr, layout)

        # controls
        cy = top + self.info_h * 0.86
        center = tx + tw / 2
        spacing = 46 * u
        play_r = (17 + 2.5 * self._hovered("play_pause")) * u
        cr.arc(center, cy, play_r, 0, 2 * math.pi)
        cr.set_source_rgba(*ink, 1)
        cr.fill()
        cr.set_source_rgba(*self.surface[:3], 1)
        icon(
            cr,
            "pause" if self.status == "Playing" else "play",
            center + (0 if self.status == "Playing" else 1.5 * u),
            cy,
            13 * u,
        )
        self._hits.append(
            ("play_pause", (center - play_r, cy - play_r, play_r * 2, play_r * 2))
        )
        for action, x in (("previous", center - spacing), ("next", center + spacing)):
            if glow := self._hovered(action):
                cr.arc(x, cy, 17 * u, 0, 2 * math.pi)
                cr.set_source_rgba(*ink, 0.1 * glow)
                cr.fill()
            cr.set_source_rgba(*ink, 1)
            icon(cr, action, x, cy, 15 * u)
            self._hits.append((action, (x - 16 * u, cy - 16 * u, 32 * u, 32 * u)))

        if self._has_lyrics_section:
            self._draw_lyrics(cr)
        return False

    def _lyric_layout(
        self, cr: cairo.Context, text: str, size: float, weight: float, width: float
    ) -> Pango.Layout:
        """Lyric layouts, cached: only lines mid-transition change size."""
        key = (text, round(size * 4), round(weight), round(width))
        layout = self._layouts.get(key)
        if layout is None:
            layout = text_layout(
                cr, text, size, weight, width, Pango.Alignment.CENTER, wrap=True
            )
            if len(self._layouts) > 96:
                self._layouts.clear()
            self._layouts[key] = layout
        else:
            PangoCairo.update_layout(cr, layout)
        return layout

    def _draw_seek(self, cr: cairo.Context):
        """
        The level bars, solid up to the playhead and faint after it (flat when
        quiet), the playhead, and on hover a ghost playhead with its time.
        """
        if self._seek_geometry is None:
            return
        tx, tw, bar_y = self._seek_geometry
        ink, u = self.ink, self.u
        bar_w, bar_gap = SEEK_BAR_W * u, SEEK_BAR_GAP * u
        count = max(8, int((tw + bar_gap) / (bar_w + bar_gap)))
        if len(self._levels) != count:
            self._levels = [0.0] * count
        step = (tw - bar_w) / (count - 1)
        played = tw * self.progress
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(bar_w)
        for i, level in enumerate(self._levels):
            x = tx + bar_w / 2 + i * step
            half = 1.2 * u + level * SEEK_BAR_MAX * u
            cr.move_to(x, bar_y - half)
            cr.line_to(x, bar_y + half)
            cr.set_source_rgba(*ink, 0.9 if x <= tx + played else 0.2)
            cr.stroke()
        # the playhead: a slim line standing a little taller than the bars,
        # thicker while scrubbing
        head_x = tx + played
        head_half = (SEEK_BAR_MAX + 3) * u
        cr.set_line_width((3.2 if self._scrub is not None else 2.2) * u)
        cr.set_source_rgba(*ink, 1)
        cr.move_to(head_x, bar_y - head_half)
        cr.line_to(head_x, bar_y + head_half)
        cr.stroke()
        self._seek_rect = (tx, bar_y - 16 * u, tw, 32 * u)
        if (glow := self._hovered("seek")) and self._scrub is None and self.length:
            # where a click would land, and when that is
            ghost_x = max(tx, min(tx + tw, self._hover_x))
            cr.set_line_width(1.6 * u)
            cr.set_source_rgba(*ink, 0.45 * glow)
            cr.move_to(ghost_x, bar_y - head_half)
            cr.line_to(ghost_x, bar_y + head_half)
            cr.stroke()
            label = format_time(self._seek_fraction(ghost_x) * self.length)
            layout = text_layout(cr, label, 10.5 * u, 600)
            lw, lh = layout.get_pixel_size()
            bx = max(tx, min(tx + tw - lw - 10 * u, ghost_x - lw / 2 - 5 * u))
            # above the bar, under the artist line
            by = bar_y - head_half - lh - 7 * u
            rounded_rect(cr, bx, by, lw + 10 * u, lh + 4 * u, (lh + 4 * u) / 2)
            cr.set_source_rgba(*ink, 0.9 * glow)
            cr.fill()
            cr.set_source_rgba(*self.surface[:3], glow)
            cr.move_to(bx + 5 * u, by + 2 * u)
            PangoCairo.show_layout(cr, layout)

    def _seek_only_area(self) -> tuple[int, int, int, int] | None:
        """The rectangle a level-only frame needs repainting, if it can."""
        if self._seek_geometry is None or self._seek_rect[2] <= 0:
            return None
        x, y, w, h = self._seek_rect
        return (int(x) - 4, int(y) - 2, int(w) + 8, int(h) + 4)

    def _draw_switch_icon(self, cr: cairo.Context, cx: float, cy: float, size: float):
        """Two opposing arrows: switch to the next player."""
        s = size / 2
        cr.set_source_rgba(*self.ink, 0.85 if self.source_count > 1 else 0.3)
        cr.set_line_width(1.8 * self.u)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        for y, direction in ((cy - s * 0.4, 1), (cy + s * 0.4, -1)):
            cr.move_to(cx - direction * s, y)
            cr.line_to(cx + direction * s, y)
            cr.move_to(cx + direction * (s - s * 0.45), y - s * 0.4)
            cr.line_to(cx + direction * s, y)
            cr.line_to(cx + direction * (s - s * 0.45), y + s * 0.4)
        cr.stroke()

    def _draw_lyrics_icon(self, cr: cairo.Context, cx: float, cy: float, size: float):
        """Three text lines, the middle one short: lyrics on/off."""
        s = size / 2
        cr.set_source_rgba(*self.ink, 0.85 if self.show_lyrics else 0.3)
        cr.set_line_width(1.8 * self.u)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for dy, length in ((-0.6, 1.0), (0, 0.6), (0.6, 0.85)):
            cr.move_to(cx - s, cy + dy * s)
            cr.line_to(cx - s + 2 * s * length, cy + dy * s)
        cr.stroke()

    def _draw_lyrics(self, cr: cairo.Context):
        """Previous, current and next lines; changes glide, never snap."""
        x0 = self.gap
        width = self.card_w - x0 * 2
        top, h = self.lyrics_top, self.lyrics_h

        # a hairline between the player and its lyrics
        cr.set_source_rgba(*self.ink, 0.08)
        cr.rectangle(x0, top - self.gap // 4, width, 1)
        cr.fill()

        cr.save()
        cr.rectangle(0, top, self.card_w, h)
        cr.clip()
        line_h = h / 3
        center = top + h / 2
        cr.push_group()

        # `t` is how far into a change we are: the outgoing line shrinks,
        # lightens and dims while the new one grows into the accent, and the
        # view scrolls from one to the other
        t = 1 - self._lyric_slide
        t = t * t * (3 - 2 * t)
        index = self._lyric_index
        blocks: list[tuple[int, Pango.Layout, float, float]] = []
        for delta in (-2, -1, 0, 1, 2):
            text = self.media.lyric_at(index + delta)
            if delta == 0 and not text:
                text = "♪"
            if not text:
                continue
            focus = t if delta == 0 else (1 - t) if delta == -1 else 0.0
            size = line_h * (
                LYRIC_SIZE_OTHER + (LYRIC_SIZE_CURRENT - LYRIC_SIZE_OTHER) * focus
            )
            weight = (
                LYRIC_WEIGHT_OTHER + (LYRIC_WEIGHT_CURRENT - LYRIC_WEIGHT_OTHER) * focus
            )
            layout = self._lyric_layout(cr, text, size, weight, width)
            blocks.append((delta, layout, float(layout.get_pixel_size()[1]), focus))

        gap = line_h * 0.18
        positions: dict[int, float] = {}
        y = 0.0
        for delta, _layout, block_h, _focus in blocks:
            positions[delta] = y
            y += block_h + gap
        middles = {d: positions[d] + bh / 2 for d, _l, bh, _f in blocks}
        new_middle = middles.get(0, 0.0)
        old_middle = middles.get(-1, new_middle - line_h)
        offset = center - (old_middle + (new_middle - old_middle) * t)

        for delta, layout, _block_h, focus in blocks:
            r, g, b = (
                self.ink[i] + (self.accent[i] - self.ink[i]) * focus for i in range(3)
            )
            cr.set_source_rgba(r, g, b, 0.5 + 0.5 * focus)
            cr.move_to(x0, positions[delta] + offset)
            PangoCairo.show_layout(cr, layout)

        # fade toward the section's edges so lines dissolve, not get cut
        cr.pop_group_to_source()
        fade = cairo.LinearGradient(0, top, 0, top + h)
        fade.add_color_stop_rgba(0, 0, 0, 0, 0)
        fade.add_color_stop_rgba(0.22, 0, 0, 0, 1)
        fade.add_color_stop_rgba(0.78, 0, 0, 0, 1)
        fade.add_color_stop_rgba(1, 0, 0, 0, 0)
        cr.mask(fade)
        cr.restore()


class MusicPlayerWindow(WaylandWindow):
    """
    The card in a window of its own on the desktop layer. Dragging moves the
    window by changing its layer-shell margins.
    """

    def __init__(
        self,
        monitor: int,
        monitor_name: str,
        geometry: Gdk.Rectangle,
        media,
        cava,
        position: list[int] | None,
        on_moved: Callable[["MusicPlayerWindow"], None],
        on_toggle_lyrics: Callable[["MusicPlayerWindow"], None],
    ):
        self.monitor_name = monitor_name
        self.geometry = geometry
        self.player = MusicPlayer(
            media,
            cava,
            on_move_by=self.move_by,
            on_moved=lambda: on_moved(self),
            on_resize=self._apply_position,
            on_toggle_lyrics=lambda: on_toggle_lyrics(self),
        )
        if position:
            self.x, self.y = position
        else:
            # bottom-left, above the visualizer
            self.x = round(geometry.height * 0.06)
            self.y = (
                geometry.height - self.player.total_h - round(geometry.height * 0.16)
            )
        super().__init__(
            title="fabric-music",
            layer="bottom",
            anchor="top left",
            exclusivity="none",
            keyboard_mode="none",
            monitor=monitor,
            child=self.player,
        )
        self._apply_position()
        self.show_all()

    def _apply_position(self):
        # stay on screen, including when the lyrics section comes or goes
        self.x = max(0, min(self.x, self.geometry.width - self.player.card_w))
        self.y = max(0, min(self.y, self.geometry.height - self.player.total_h))
        self.margin = (self.y, 0, 0, self.x)

    def move_by(self, dx: int, dy: int):
        self.x += dx
        self.y += dy
        self._apply_position()
