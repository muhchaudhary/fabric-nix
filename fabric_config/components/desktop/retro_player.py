"""
A retro media player for the desktop, drawn with cairo in one of several
themes: a click-wheel MP3 player, a cassette tape, a turntable. It shows the
current MPRIS player's track and art, and its controls work: click the
buttons (or the wheel), drag it anywhere else to move it.
"""

import math
import os
import threading
import urllib.request
from collections.abc import Callable

import cairo
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
from fabric.widgets.wayland import WaylandWindow
from loguru import logger

from fabric_config.utils.uri import file_uri_to_path

THEMES = ("mp3", "cassette", "vinyl")
THEME_LABELS = {"mp3": "MP3 player", "cassette": "Cassette", "vinyl": "Turntable"}
# (width, height) as fractions of the monitor height
THEME_SIZES = {"mp3": (0.17, 0.29), "cassette": (0.33, 0.25), "vinyl": (0.44, 0.25)}

MEDIA_CACHE = os.path.join(GLib.get_user_cache_dir(), "fabric", "media")
FRAME_MS = 33
DRAG_THRESHOLD = 6
VINYL_SPEED = 2 * math.pi * 33.3 / 60  # 33⅓ rpm, in radians per second
REEL_SPEED = 2.2
# the record's centre label (the album art), as a fraction of its radius
VINYL_LABEL = 0.6


# Drawing helpers


def rounded_rect(cr: cairo.Context, x: float, y: float, w: float, h: float, r: float):
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def rgb(hex_color: str) -> tuple[float, float, float]:
    value = hex_color.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def fit(cr: cairo.Context, text: str, max_width: float) -> str:
    """`text`, cut short with an ellipsis to fit `max_width`."""
    if cr.text_extents(text).x_advance <= max_width:
        return text
    while text and cr.text_extents(text + "…").x_advance > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


def font(cr: cairo.Context, size: float, bold: bool = False, family: str = "Inter"):
    cr.select_font_face(
        family,
        cairo.FONT_SLANT_NORMAL,
        cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL,
    )
    cr.set_font_size(size)


def text_at(cr: cairo.Context, text: str, x: float, y: float, align: str = "left"):
    extents = cr.text_extents(text)
    if align == "center":
        x -= extents.x_advance / 2
    elif align == "right":
        x -= extents.x_advance
    cr.move_to(x, y)
    cr.show_text(text)


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
    """
    Draw a media icon centred on (cx, cy) in the current source. Shapes, not
    glyphs: Inter has no media symbols, and cairo's toy text API can't fall
    back to a font that does.
    """
    s = size / 2
    match kind:
        case "play":
            cr.move_to(cx - s * 0.6, cy - s)
            cr.line_to(cx + s * 0.9, cy)
            cr.line_to(cx - s * 0.6, cy + s)
            cr.close_path()
        case "pause":
            cr.rectangle(cx - s * 0.75, cy - s, s * 0.5, s * 2)
            cr.rectangle(cx + s * 0.25, cy - s, s * 0.5, s * 2)
        case "stop":
            cr.rectangle(cx - s * 0.8, cy - s * 0.8, s * 1.6, s * 1.6)
        case "next" | "previous":
            d = 1 if kind == "next" else -1
            cr.move_to(cx - d * s, cy - s * 0.85)
            cr.line_to(cx + d * s * 0.45, cy)
            cr.line_to(cx - d * s, cy + s * 0.85)
            cr.close_path()
            bar_x = cx + d * s * 0.45 - (s * 0.3 if d > 0 else 0)
            cr.rectangle(bar_x, cy - s * 0.85, s * 0.3, s * 1.7)
        case "play_pause":
            icon(cr, "play", cx - s * 0.55, cy, size * 0.6)
            icon(cr, "pause", cx + s * 0.6, cy, size * 0.6)
            return
    cr.fill()


def format_time(microseconds: float) -> str:
    seconds = max(0, int(microseconds // 1_000_000))
    return f"{seconds // 60}:{seconds % 60:02}"


# Album art


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
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 300, 300, True)
        except Exception as e:
            logger.debug(f"[Retro player] No art from {url}: {e}")
        GLib.idle_add(lambda: callback(pixbuf) or False)

    threading.Thread(target=work, daemon=True).start()


# The widget


class RetroPlayer(Gtk.EventBox):
    """
    The player card: a glass panel in the theme's colours holding the source
    chip (player switcher), the device, and the synced lyrics.
    """

    def __init__(
        self,
        monitor_height: int,
        theme: str,
        media,  # MediaState
        on_move_by: Callable[[int, int], None],
        on_moved: Callable[[], None],
        on_cycle_theme: Callable[[], None],
    ):
        super().__init__()
        self.set_name("retro-player")
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.SMOOTH_SCROLL_MASK
        )
        self.monitor_height = monitor_height
        self.media = media
        self._on_move_by = on_move_by
        self._on_moved = on_moved
        self._on_cycle_theme = on_cycle_theme

        self.area = Gtk.DrawingArea()
        self.add(self.area)
        self.area.connect("draw", self._on_draw)
        self.connect("button-press-event", self._on_press)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("button-release-event", self._on_release)
        self.connect("scroll-event", self._on_scroll)

        # track state
        self.title = ""
        self.artist = ""
        self.status = "Stopped"
        self.length = 0
        self.source = ""  # the player's name, e.g. "spotify"
        self.source_count = 0
        self._art_url: str | None = None
        self.art: GdkPixbuf.Pixbuf | None = None

        # palette, from the bar's theme and the wallpaper accent
        self.is_light = False
        self.accent = (0.75, 0.8, 0.95)
        self.show_lyrics = True

        # lyrics: the line being sung, and a slide when it changes
        self._lyric_index = -1
        self._lyric_slide = 0.0  # 1 -> 0 as a new line slides into place
        self._lyrics_poll: int | None = None

        # animation
        self.visible_on_desktop = True
        self._angle = 0.0
        self._speed = 0.0
        self._tick_id: int | None = None
        self._last_tick: float | None = None

        # input; positions are window-local (Wayland has no global pointer
        # position), and the window follows the pointer while dragging
        self._hits: list[tuple[str, tuple]] = []
        self._press: tuple[float, float] | None = None
        self._dragged = 0.0
        self._dragging = False

        self.theme = ""
        self.set_theme(theme)
        GLib.timeout_add_seconds(1, self._second)

    # Layout

    def set_theme(self, theme: str):
        self.theme = theme if theme in THEMES else THEMES[0]
        mh = self.monitor_height
        w, h = THEME_SIZES[self.theme]
        # the device
        self.width = round(mh * w)
        self.height = round(mh * h)
        # the card around it
        self.pad = round(mh * 0.018)
        self.chip_h = round(mh * 0.03)
        self.lyrics_h = round(mh * 0.115)
        self.card_w = max(round(mh * 0.36), self.width) + 2 * self.pad
        self.card_h = (
            self.pad + self.chip_h + self.pad + self.height + self.pad
            + self.lyrics_h + self.pad
        )  # fmt: skip
        self.device_x = (self.card_w - self.width) / 2
        self.device_y = self.pad + self.chip_h + self.pad
        self.area.set_size_request(self.card_w, self.card_h)
        self.queue_draw()

    @property
    def total_height(self) -> int:
        return self.card_h

    def set_palette(self, is_light: bool, accent: tuple[float, float, float] | None):
        self.is_light = is_light
        if accent is not None:
            self.accent = accent
        self.queue_draw()

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
        self._update_animation()
        self._update_lyrics_poll()
        self.queue_draw()

    def _set_art(self, url: str | None):
        if url == self._art_url:
            return
        self._art_url = url
        self.art = None

        def done(pixbuf):
            if url == self._art_url:
                self.art = pixbuf
                self.queue_draw()

        load_art(url, done)

    @property
    def position(self) -> float:
        """Estimated position in microseconds."""
        return self.media.position

    @property
    def progress(self) -> float:
        return min(1.0, self.position / self.length) if self.length else 0.0

    # Lyrics

    def _update_lyrics_poll(self):
        wanted = (
            self.show_lyrics
            and bool(self.media.lyrics)
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
            self._update_animation()
        return True

    def lyrics_changed(self):
        self._lyric_index = self.media.lyric_index()
        self._update_lyrics_poll()
        self.queue_draw()

    # Animation

    def set_desktop_visible(self, visible: bool):
        self.visible_on_desktop = visible
        self._update_animation()
        self._update_lyrics_poll()

    def _update_animation(self):
        spinning = self.theme in ("cassette", "vinyl") and (
            self.status == "Playing" or self._speed > 0.01
        )
        sliding = self._lyric_slide > 0
        wanted = (spinning or sliding) and self.visible_on_desktop
        if wanted and self._tick_id is None:
            self._last_tick = None
            self._tick_id = GLib.timeout_add(FRAME_MS, self._tick)

    def _tick(self):
        now = GLib.get_monotonic_time() / 1e6
        dt = min(0.1, now - self._last_tick) if self._last_tick else FRAME_MS / 1000
        self._last_tick = now
        target = (VINYL_SPEED if self.theme == "vinyl" else REEL_SPEED) * (
            1 if self.status == "Playing" else 0
        )
        # a record takes a moment to come up to speed and to wind down
        self._speed += (target - self._speed) * min(1.0, dt * 3)
        self._angle = (self._angle + self._speed * dt) % (2 * math.pi)
        self._lyric_slide = max(0.0, self._lyric_slide - dt / 0.35)
        self.queue_draw()
        spinning = self.theme in ("cassette", "vinyl") and (
            self.status == "Playing" or self._speed > 0.01
        )
        if not (spinning and self.visible_on_desktop) and self._lyric_slide <= 0:
            if self.status != "Playing":
                self._speed = 0.0
            self._tick_id = None
            return False
        return True

    def _second(self):
        # progress bars move on their own between track updates
        if (
            self.status == "Playing"
            and self.visible_on_desktop
            and self._tick_id is None
        ):
            self.queue_draw()
        return True

    # Input

    def _on_press(self, _widget, event: Gdk.EventButton):
        if event.button != 1:
            return False
        self._press = (event.x, event.y)
        self._dragged = 0.0
        self._dragging = False
        return True

    def _on_motion(self, _widget, event: Gdk.EventMotion):
        if self._press is None:
            return False
        dx, dy = event.x - self._press[0], event.y - self._press[1]
        self._dragged += math.hypot(dx, dy)
        if not self._dragging and self._dragged > DRAG_THRESHOLD:
            self._dragging = True
        if self._dragging and (dx or dy):
            # the window moves under the pointer, so the press point stays
            # put in window coordinates
            self._on_move_by(round(dx), round(dy))
        return True

    def _on_release(self, _widget, event: Gdk.EventButton):
        if self._press is None:
            return False
        self._press = None
        if self._dragging:
            self._dragging = False
            self._on_moved()
            return True
        if action := self._hit(event.x, event.y):
            self._act(action)
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

    def _hit(self, x: float, y: float) -> str | None:
        for action, shape in self._hits:
            match shape:
                case ("rect", rx, ry, rw, rh) if (
                    rx <= x <= rx + rw and ry <= y <= ry + rh
                ):
                    return action
                case ("circle", cx, cy, r) if math.hypot(x - cx, y - cy) <= r:
                    return action
                case ("wheel", cx, cy, inner, outer):
                    distance = math.hypot(x - cx, y - cy)
                    if distance <= inner:
                        return "play_pause"
                    if distance <= outer:
                        angle = math.degrees(math.atan2(y - cy, x - cx))
                        if -45 <= angle < 45:
                            return "next"
                        if 45 <= angle < 135:
                            return "play_pause"
                        if -135 <= angle < -45:
                            return "menu"
                        return "previous"
        return None

    def _act(self, action: str):
        if action == "menu":
            self._on_cycle_theme()
            return
        if action in ("prev_source", "next_source"):
            self.media.cycle_player(-1 if action == "prev_source" else 1)
            return
        player = self.media.current_player()
        if player is None:
            return
        method = getattr(player, action, None)
        if callable(method):
            method()

    # Drawing

    @property
    def ink(self) -> tuple[float, float, float]:
        """The theme's foreground (--fg)."""
        return rgb("#4c4f69") if self.is_light else rgb("#cdd6f4")

    def _on_draw(self, _widget, cr: cairo.Context):
        self._hits = []
        self._draw_card(cr)
        self._draw_chip(cr)
        # the device draws in its own coordinates; shift its hit areas after
        device_hits = len(self._hits)
        cr.save()
        cr.translate(self.device_x, self.device_y)
        {
            "mp3": self._draw_mp3,
            "cassette": self._draw_cassette,
            "vinyl": self._draw_vinyl,
        }[self.theme](cr, self.width, self.height)
        cr.restore()
        for i in range(device_hits, len(self._hits)):
            action, (kind, x, y, *rest) = self._hits[i]
            self._hits[i] = (
                action,
                (kind, x + self.device_x, y + self.device_y, *rest),
            )
        self._draw_lyrics(cr)
        return False

    def _draw_card(self, cr: cairo.Context):
        """The glass panel, like the bar's popups (--bg-glass)."""
        radius = self.monitor_height * 0.022
        rounded_rect(cr, 0.5, 0.5, self.card_w - 1, self.card_h - 1, radius)
        if self.is_light:
            cr.set_source_rgba(*rgb("#e6e9ef"), 0.88)
        else:
            cr.set_source_rgba(0, 0, 0, 0.5)
        cr.fill_preserve()
        cr.set_source_rgba(*self.ink, 0.1)
        cr.set_line_width(1)
        cr.stroke()

    def _draw_chip(self, cr: cairo.Context):
        """The player's name, with arrows to switch when there are several."""
        h = self.chip_h
        y = self.pad
        label = self.source.capitalize() if self.source else "No player"
        font(cr, h * 0.48, bold=True)
        arrows = self.source_count > 1
        text_w = cr.text_extents(label).x_advance
        inner = h * 0.7
        chip_w = text_w + inner * 2 + (h * 1.4 if arrows else 0)
        x = (self.card_w - chip_w) / 2
        rounded_rect(cr, x, y, chip_w, h, h / 2)
        cr.set_source_rgba(*self.accent, 0.18)
        cr.fill()
        cr.set_source_rgba(*self.ink, 0.95)
        text_at(cr, label, self.card_w / 2, y + h * 0.66, "center")
        if not arrows:
            return
        cy = y + h / 2
        cr.set_line_width(2)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        for action, ax, direction in (
            ("prev_source", x + inner * 0.8, -1),
            ("next_source", x + chip_w - inner * 0.8, 1),
        ):
            cr.move_to(ax - direction * h * 0.1, cy - h * 0.18)
            cr.line_to(ax + direction * h * 0.1, cy)
            cr.line_to(ax - direction * h * 0.1, cy + h * 0.18)
            cr.stroke()
            self._hits.append((action, ("rect", ax - h * 0.55, y, h * 1.1, h)))

    def _draw_lyrics(self, cr: cairo.Context):
        """Previous, current and next lines; a new line slides up into place."""
        x0 = self.pad * 1.5
        width = self.card_w - x0 * 2
        top = self.device_y + self.height + self.pad
        h = self.lyrics_h
        cr.save()
        cr.rectangle(0, top, self.card_w, h)
        cr.clip()
        line_h = h / 3
        center = top + h / 2
        if not self.show_lyrics or not self.media.lyrics:
            cr.set_source_rgba(*self.ink, 0.4)
            font(cr, line_h * 0.42)
            message = (
                "Lyrics off"
                if not self.show_lyrics
                else ("No synced lyrics" if self.title else "")
            )
            text_at(cr, message, self.card_w / 2, center + line_h * 0.15, "center")
            cr.restore()
            return
        eased = self._lyric_slide * self._lyric_slide * (3 - 2 * self._lyric_slide)
        offset = eased * line_h
        index = self._lyric_index
        for delta in (-2, -1, 0, 1, 2):
            text = self.media.lyric_at(index + delta)
            if delta == 0 and not text:
                text = "♪"
            if not text:
                continue
            y = center + delta * line_h + offset
            distance = abs((y - center) / line_h)
            current = delta == 0
            size = line_h * (0.52 if current else 0.4)
            font(cr, size, bold=current)
            alpha = max(0.0, 1 - distance * 0.6) * (1 if current else 0.75)
            if current:
                cr.set_source_rgba(*self.accent, alpha)
            else:
                cr.set_source_rgba(*self.ink, alpha * 0.7)
            text_at(
                cr, fit(cr, text, width), self.card_w / 2, y + size * 0.35, "center"
            )
        cr.restore()

    def _track_lines(self) -> tuple[str, str]:
        if not self.title:
            return "Nothing playing", "Play something to begin"
        return self.title, self.artist or "Unknown artist"

    # MP3 player: white body, LCD, click wheel

    def _draw_mp3(self, cr: cairo.Context, w: float, h: float):
        pad = w * 0.07
        rounded_rect(cr, 1, 1, w - 2, h - 2, w * 0.1)
        body = cairo.LinearGradient(0, 0, w, h)
        body.add_color_stop_rgb(0, *rgb("#fbfbfc"))
        body.add_color_stop_rgb(1, *rgb("#d9dbe0"))
        cr.set_source(body)
        cr.fill_preserve()
        cr.set_source_rgba(0, 0, 0, 0.18)
        cr.set_line_width(1)
        cr.stroke()

        # screen
        sx, sy, sw, sh = pad, pad, w - 2 * pad, h * 0.4
        rounded_rect(cr, sx - 2, sy - 2, sw + 4, sh + 4, w * 0.035)
        cr.set_source_rgb(*rgb("#2a2c31"))
        cr.fill()
        rounded_rect(cr, sx, sy, sw, sh, w * 0.025)
        lcd = cairo.LinearGradient(0, sy, 0, sy + sh)
        lcd.add_color_stop_rgb(0, *rgb("#eef4fb"))
        lcd.add_color_stop_rgb(1, *rgb("#cfdcea"))
        cr.set_source(lcd)
        cr.fill()

        ink = rgb("#1d2733")
        unit = sh / 10
        # header bar
        cr.set_source_rgba(*ink, 0.1)
        cr.rectangle(sx, sy, sw, unit * 1.6)
        cr.fill()
        cr.set_source_rgb(*ink)
        font(cr, unit * 0.95, bold=True)
        text_at(cr, "Now Playing", sx + sw / 2, sy + unit * 1.15, "center")
        icon(
            cr,
            "play" if self.status == "Playing" else "pause",
            sx + unit * 0.9,
            sy + unit * 0.8,
            unit * 0.75,
        )
        # battery
        bx, by = sx + sw - unit * 2.1, sy + unit * 0.45
        cr.set_line_width(1)
        cr.rectangle(bx, by, unit * 1.4, unit * 0.7)
        cr.stroke()
        cr.rectangle(bx + 1.5, by + 1.5, unit * 1.0, unit * 0.7 - 3)
        cr.fill()
        cr.rectangle(bx + unit * 1.4, by + unit * 0.2, 2, unit * 0.3)
        cr.fill()

        # art + text
        art = unit * 3.9
        ax, ay = sx + unit * 0.6, sy + unit * 2.2
        if self.art is not None:
            cr.save()
            rounded_rect(cr, ax, ay, art, art, 3)
            cr.clip()
            paint_pixbuf(cr, self.art, ax, ay, art)
            cr.restore()
        else:
            rounded_rect(cr, ax, ay, art, art, 3)
            cr.set_source_rgba(*ink, 0.12)
            cr.fill()
            cr.set_source_rgba(*ink, 0.5)
            font(cr, art * 0.5)
            text_at(cr, "♪", ax + art / 2, ay + art * 0.68, "center")
        title, artist = self._track_lines()
        tx = ax + art + unit * 0.6
        text_width = sx + sw - tx - unit * 0.5
        cr.set_source_rgb(*ink)
        font(cr, unit * 1.05, bold=True)
        text_at(cr, fit(cr, title, text_width), tx, ay + unit * 1.2)
        font(cr, unit * 0.9)
        cr.set_source_rgba(*ink, 0.75)
        text_at(cr, fit(cr, artist, text_width), tx, ay + unit * 2.5)

        # progress
        py = sy + sh - unit * 1.9
        cr.set_source_rgba(*ink, 0.15)
        rounded_rect(cr, sx + unit * 0.6, py, sw - unit * 1.2, unit * 0.55, unit * 0.27)
        cr.fill()
        cr.set_source_rgba(*self.accent, 0.95)
        rounded_rect(
            cr,
            sx + unit * 0.6,
            py,
            max(unit * 0.55, (sw - unit * 1.2) * self.progress),
            unit * 0.55,
            unit * 0.27,
        )
        cr.fill()
        cr.set_source_rgba(*ink, 0.8)
        font(cr, unit * 0.75)
        if self.length:
            text_at(cr, format_time(self.position), sx + unit * 0.6, py + unit * 1.45)
            text_at(
                cr,
                "-" + format_time(self.length - self.position),
                sx + sw - unit * 0.6,
                py + unit * 1.45,
                "right",
            )

        # click wheel
        cx, cy = w / 2, sy + sh + (h - sy - sh) / 2
        outer = min(w - 2 * pad, h - sy - sh - pad) / 2
        inner = outer * 0.38
        cr.arc(cx, cy, outer, 0, 2 * math.pi)
        wheel = cairo.LinearGradient(0, cy - outer, 0, cy + outer)
        wheel.add_color_stop_rgb(0, *rgb("#f1f2f4"))
        wheel.add_color_stop_rgb(1, *rgb("#e1e3e7"))
        cr.set_source(wheel)
        cr.fill_preserve()
        cr.set_source_rgba(0, 0, 0, 0.1)
        cr.stroke()
        cr.arc(cx, cy, inner, 0, 2 * math.pi)
        center = cairo.LinearGradient(0, cy - inner, 0, cy + inner)
        center.add_color_stop_rgb(0, *rgb("#dfe1e5"))
        center.add_color_stop_rgb(1, *rgb("#fafbfc"))
        cr.set_source(center)
        cr.fill_preserve()
        cr.set_source_rgba(0, 0, 0, 0.12)
        cr.stroke()

        label = rgb("#9aa0a8")
        cr.set_source_rgb(*label)
        font(cr, outer * 0.16, bold=True)
        text_at(cr, "MENU", cx, cy - outer * 0.66, "center")
        icon(cr, "previous", cx - outer * 0.7, cy, outer * 0.16)
        icon(cr, "next", cx + outer * 0.7, cy, outer * 0.16)
        icon(cr, "play_pause", cx, cy + outer * 0.7, outer * 0.16)
        self._hits.append(("wheel", ("wheel", cx, cy, inner, outer)))

    # Cassette: smoky shell, label, spinning reels, piano keys

    def _draw_cassette(self, cr: cairo.Context, w: float, h: float):
        keys_h = h * 0.16
        bh = h - keys_h - 4
        r = w * 0.04
        rounded_rect(cr, 1, 1, w - 2, bh, r)
        shell = cairo.LinearGradient(0, 0, 0, bh)
        shell.add_color_stop_rgba(0, *rgb("#3b3b42"), 0.96)
        shell.add_color_stop_rgba(1, *rgb("#202025"), 0.96)
        cr.set_source(shell)
        cr.fill()
        # screws
        cr.set_source_rgba(1, 1, 1, 0.25)
        for sx, sy in (
            (r * 1.2, r * 1.2),
            (w - r * 1.2, r * 1.2),
            (r * 1.2, bh - r * 1.2),
            (w - r * 1.2, bh - r * 1.2),
        ):
            cr.arc(sx, sy, w * 0.009, 0, 2 * math.pi)
            cr.fill()

        # label
        lx, ly, lw, lh = w * 0.07, bh * 0.08, w * 0.86, bh * 0.62
        rounded_rect(cr, lx, ly, lw, lh, r * 0.6)
        cr.set_source_rgb(*rgb("#f3ead2"))
        cr.fill()
        stripe_y = ly + lh * 0.8
        for i, color in enumerate((self.accent, rgb("#f0a63a"), rgb("#3f8fb3"))):
            cr.set_source_rgb(*color)
            cr.rectangle(lx, stripe_y + i * lh * 0.05, lw, lh * 0.05)
            cr.fill()
        title, artist = self._track_lines()
        ink = rgb("#2b2620")
        cr.set_source_rgb(*ink)
        font(cr, lh * 0.14, bold=True)
        text_at(cr, fit(cr, title, lw * 0.8), lx + lw * 0.06, ly + lh * 0.2)
        font(cr, lh * 0.1)
        cr.set_source_rgba(*ink, 0.75)
        text_at(cr, fit(cr, artist, lw * 0.82), lx + lw * 0.06, ly + lh * 0.34)
        font(cr, lh * 0.12, bold=True)
        cr.set_source_rgba(*ink, 0.8)
        text_at(cr, "A", lx + lw * 0.94, ly + lh * 0.2, "right")

        # window with reels
        wx, wy, ww, wh = w * 0.27, ly + lh * 0.43, w * 0.46, lh * 0.3
        rounded_rect(cr, wx, wy, ww, wh, wh / 2)
        cr.set_source_rgba(0.08, 0.08, 0.1, 0.92)
        cr.fill()
        reel_r = wh * 0.32
        left = (wx + wh * 0.5, wy + wh / 2)
        right = (wx + ww - wh * 0.5, wy + wh / 2)
        progress = self.progress
        tape_max = wh * 0.95
        for (cx, cy), amount in ((left, 1 - progress), (right, progress)):
            # wound tape
            cr.arc(cx, cy, reel_r + (tape_max - reel_r) * amount * 0.55, 0, 2 * math.pi)
            cr.set_source_rgb(*rgb("#4a3424"))
            cr.fill()
        cr.save()
        rounded_rect(cr, wx, wy, ww, wh, wh / 2)
        cr.clip()
        for cx, cy in (left, right):
            cr.arc(cx, cy, reel_r, 0, 2 * math.pi)
            cr.set_source_rgb(*rgb("#eeeeee"))
            cr.fill()
            cr.set_source_rgb(*rgb("#1a1a1e"))
            cr.arc(cx, cy, reel_r * 0.42, 0, 2 * math.pi)
            cr.fill()
            cr.set_line_width(reel_r * 0.16)
            cr.set_source_rgb(*rgb("#eeeeee"))
            for i in range(6):
                a = self._angle + i * math.pi / 3
                cr.move_to(
                    cx + math.cos(a) * reel_r * 0.15, cy + math.sin(a) * reel_r * 0.15
                )
                cr.line_to(
                    cx + math.cos(a) * reel_r * 0.42, cy + math.sin(a) * reel_r * 0.42
                )
                cr.stroke()
        cr.restore()

        # bottom trapezoid with tape guides
        tx = w * 0.2
        cr.move_to(tx, bh)
        cr.line_to(tx + w * 0.05, bh * 0.8)
        cr.line_to(w - tx - w * 0.05, bh * 0.8)
        cr.line_to(w - tx, bh)
        cr.close_path()
        cr.set_source_rgba(1, 1, 1, 0.08)
        cr.fill()
        cr.set_source_rgba(0, 0, 0, 0.6)
        for gx in (0.32, 0.45, 0.55, 0.68):
            cr.arc(w * gx, bh * 0.9, w * 0.012, 0, 2 * math.pi)
            cr.fill()

        # piano keys
        key_w = w * 0.18
        gap = w * 0.02
        start = (w - (3 * key_w + 2 * gap)) / 2
        for i, (action, glyph) in enumerate(
            (
                ("previous", "previous"),
                ("play_pause", "pause" if self.status == "Playing" else "play"),
                ("next", "next"),
            )
        ):
            kx = start + i * (key_w + gap)
            ky = bh + 4
            pressed = action == "play_pause" and self.status == "Playing"
            rounded_rect(
                cr, kx, ky + (2 if pressed else 0), key_w, keys_h - 2, keys_h * 0.2
            )
            key = cairo.LinearGradient(0, ky, 0, ky + keys_h)
            key.add_color_stop_rgb(0, *rgb("#d8d8dc" if not pressed else "#b8b8bd"))
            key.add_color_stop_rgb(1, *rgb("#a9a9af" if not pressed else "#9a9aa0"))
            cr.set_source(key)
            cr.fill()
            cr.set_source_rgb(*rgb("#2a2a2e"))
            icon(
                cr,
                glyph,
                kx + key_w / 2,
                ky + keys_h * 0.5 + (2 if pressed else 0),
                keys_h * 0.32,
            )
            self._hits.append((action, ("rect", kx, ky, key_w, keys_h)))

    # Turntable: plinth, spinning record with the art as its label, tonearm

    def _draw_vinyl(self, cr: cairo.Context, w: float, h: float):
        rounded_rect(cr, 1, 1, w - 2, h - 2, w * 0.04)
        plinth = cairo.LinearGradient(0, 0, 0, h)
        plinth.add_color_stop_rgba(0, *rgb("#3a2e26"), 0.97)
        plinth.add_color_stop_rgba(1, *rgb("#241c17"), 0.97)
        cr.set_source(plinth)
        cr.fill()

        pr = h * 0.42
        cx, cy = h * 0.5, h * 0.5
        # platter and record
        cr.arc(cx, cy, pr * 1.03, 0, 2 * math.pi)
        cr.set_source_rgb(*rgb("#8b8f94"))
        cr.fill()
        cr.arc(cx, cy, pr, 0, 2 * math.pi)
        cr.set_source_rgb(*rgb("#121214"))
        cr.fill()
        cr.set_line_width(0.6)
        # grooves fill the band between the label and the rim
        for i in range(10):
            cr.arc(cx, cy, pr * (VINYL_LABEL + 0.04 + i * 0.033), 0, 2 * math.pi)
            cr.set_source_rgba(1, 1, 1, 0.045 if i % 2 else 0.025)
            cr.stroke()
        # sheen that turns with the record
        cr.save()
        cr.translate(cx, cy)
        cr.rotate(self._angle)
        for sign in (1, -1):
            cr.move_to(0, 0)
            cr.arc(0, 0, pr * 0.98, sign * 0.15 - 0.12, sign * 0.15 + 0.12)
            cr.close_path()
            cr.set_source_rgba(1, 1, 1, 0.06)
            cr.fill()
        # label: the album art, turning
        label_r = pr * VINYL_LABEL
        cr.arc(0, 0, label_r, 0, 2 * math.pi)
        cr.clip()
        if self.art is not None:
            paint_pixbuf(cr, self.art, -label_r, -label_r, label_r * 2)
        else:
            cr.set_source_rgb(*rgb("#d9533b"))
            cr.paint()
            cr.set_source_rgba(1, 1, 1, 0.85)
            font(cr, label_r * 0.28, bold=True)
            text_at(cr, "♪", 0, label_r * 0.1, "center")
        cr.restore()
        cr.arc(cx, cy, pr * 0.03, 0, 2 * math.pi)
        cr.set_source_rgb(*rgb("#cfd3d8"))
        cr.fill()

        # tonearm: resting beside the record when idle, then tracking from
        # the outer groove inward as the song plays
        px, py = cx + pr * 1.18, h * 0.16
        if self.title and (self.status == "Playing" or self.progress > 0):
            # outer groove to just outside the label
            inner = VINYL_LABEL + 0.06
            groove = pr * (0.93 - (0.93 - inner) * self.progress)
            theta = math.radians(28)
            ex, ey = cx + groove * math.cos(theta), cy + groove * math.sin(theta)
        else:
            ex, ey = px + h * 0.03, py + h * 0.62
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(h * 0.02)
        cr.set_source_rgb(*rgb("#c9cdd2"))
        cr.move_to(px, py)
        cr.line_to(ex, ey)
        cr.stroke()
        # headshell, turned along the arm
        cr.save()
        cr.translate(ex, ey)
        cr.rotate(math.atan2(ey - py, ex - px) - math.pi / 2)
        cr.rectangle(-h * 0.022, -h * 0.01, h * 0.044, h * 0.06)
        cr.set_source_rgb(*rgb("#2c2c30"))
        cr.fill()
        cr.restore()
        cr.arc(px, py, h * 0.05, 0, 2 * math.pi)
        cr.set_source_rgb(*rgb("#9da2a8"))
        cr.fill()
        cr.arc(px, py, h * 0.022, 0, 2 * math.pi)
        cr.set_source_rgb(*rgb("#3a3a3e"))
        cr.fill()

        # title on the plinth
        title, artist = self._track_lines()
        tx = px + h * 0.12
        text_w = w - tx - w * 0.04
        cr.set_source_rgba(1, 1, 1, 0.92)
        font(cr, h * 0.06, bold=True)
        text_at(cr, fit(cr, title, text_w), tx, h * 0.36)
        cr.set_source_rgba(1, 1, 1, 0.65)
        font(cr, h * 0.048)
        text_at(cr, fit(cr, artist, text_w), tx, h * 0.45)
        if self.length:
            cr.set_source_rgba(1, 1, 1, 0.45)
            font(cr, h * 0.04)
            text_at(
                cr,
                f"{format_time(self.position)} / {format_time(self.length)}",
                tx,
                h * 0.54,
            )

        # buttons: start/stop and skip
        by = h * 0.82
        br = h * 0.045
        for i, (action, glyph) in enumerate(
            (
                ("previous", "previous"),
                ("play_pause", "stop" if self.status == "Playing" else "play"),
                ("next", "next"),
            )
        ):
            bx = tx + br + i * br * 2.8
            cr.arc(bx, by, br, 0, 2 * math.pi)
            cr.set_source_rgb(
                *(rgb("#d7dade") if action != "play_pause" else self.accent)
            )
            cr.fill()
            cr.set_source_rgb(*rgb("#1e1e22"))
            icon(cr, glyph, bx, by, br * 0.85)
            self._hits.append((action, ("circle", bx, by, br * 1.2)))
        cr.set_source_rgba(1, 1, 1, 0.4)
        font(cr, h * 0.035, bold=True)
        text_at(cr, "33 ⅓", w - w * 0.05, h * 0.95, "right")


class RetroPlayerWindow(WaylandWindow):
    """
    The player in a window of its own on the desktop layer, so its clicks and
    drags never compete with the rest of the desktop. Dragging moves the
    window by changing its layer-shell margins.
    """

    def __init__(
        self,
        monitor: int,
        monitor_name: str,
        geometry: Gdk.Rectangle,
        theme: str,
        media,
        position: list[int] | None,
        on_moved: Callable[["RetroPlayerWindow"], None],
        on_cycle_theme: Callable[[], None],
    ):
        self.monitor_name = monitor_name
        self.geometry = geometry
        self._on_moved_cb = on_moved
        self.player = RetroPlayer(
            geometry.height,
            theme,
            media,
            on_move_by=self.move_by,
            on_moved=lambda: on_moved(self),
            on_cycle_theme=on_cycle_theme,
        )
        if position:
            self.x, self.y = position
        else:
            # bottom-left, above the visualizer
            self.x = round(geometry.height * 0.06)
            self.y = (
                geometry.height - self.player.card_h - round(geometry.height * 0.16)
            )
        super().__init__(
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
        # stay on screen, including after a theme changes the card's size
        self.x = max(0, min(self.x, self.geometry.width - self.player.card_w))
        self.y = max(0, min(self.y, self.geometry.height - self.player.card_h))
        self.margin = (self.y, 0, 0, self.x)

    def move_by(self, dx: int, dy: int):
        self.x += dx
        self.y += dy
        self._apply_position()

    def set_theme(self, theme: str):
        self.player.set_theme(theme)
        self._apply_position()
