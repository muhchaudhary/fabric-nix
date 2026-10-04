"""
The bar's centre as a "dynamic island". The workspaces always stay in the
bar, with chips beside them (the focus timer while it runs, now playing while
music plays). When something happens, the pill grows downwards: a panel drops
from under it, and the pill widens to match so the two read as one shape.

Announcements queue up and show one after another: a new track, recording,
screenshots, a picked colour, caffeine, DND, Bluetooth and Wi-Fi connections,
power profiles, prayer times and a reminder before them, focus sessions.
Hovering the now-playing chip opens the media view (art, seekable progress,
controls); clicking the panel closes it.

The bar can't grow (its height is its exclusive zone, and windows would jump),
so the panel is its own layer-shell window anchored to the top, which the
compositor places right under the bar; it's only mapped while it shows.
"""

from collections.abc import Callable
from dataclasses import dataclass

import cairo
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.wayland import WaylandWindow
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

import fabric_config.config as config
from fabric_config.components.desktop.focus import get_focus_timer
from fabric_config.components.desktop.media import get_media_state
from fabric_config.components.desktop.music_player import load_art
from fabric_config.utils.color_picker import color_picker

EVENT_MS = 3500
TRACK_MS = 4500
# leaving the island closes the media view after this; brushing past doesn't
LEAVE_DELAY_MS = 400
POSITION_TICK_MS = 500
REVEAL_MS = 260
WIDEN_MS = 200
# the body's horizontal padding (#island-drop), added to its content's width
DROP_PADDING = 32
# players and devices turn up just after startup; what's already there isn't news
STARTUP_QUIET_S = 6


# Small drawn pieces


class MiniBars(Gtk.DrawingArea):
    """A few audio level bars from cava, while something plays."""

    def __init__(self, bars: int = 4, width: int = 18, height: int = 14):
        super().__init__()
        self.set_name("island-bars")
        self.set_size_request(width, height)
        self.set_valign(Gtk.Align.CENTER)
        self.count = bars
        self._owner = f"island-bars-{id(self)}"
        self._active = False
        self._handler: int | None = None
        self.connect("draw", self._on_draw)
        self.connect("unmap", lambda *_: self._want(False))
        self.connect("map", lambda *_: self._want(self._active))
        self.show()

    def set_active(self, active: bool):
        self._active = active
        self._want(active and self.get_mapped())
        self.queue_draw()

    def _want(self, wanted: bool):
        config.cava.set_wanted(self._owner, wanted)
        if wanted and self._handler is None:
            self._handler = config.cava.connect("frame", lambda *_: self.queue_draw())
        elif not wanted and self._handler is not None:
            config.cava.disconnect(self._handler)
            self._handler = None

    def _levels(self) -> list[float]:
        bars = config.cava.bars
        if not self._active or not bars:
            return [0.12] * self.count
        # the low and middle bands move the most; skip the quiet top end
        span = len(bars) // 2
        group = max(1, span // self.count)
        return [
            max(0.12, sum(bars[i * group : (i + 1) * group]) / group / 1000)
            for i in range(self.count)
        ]

    def _on_draw(self, _widget, cr: cairo.Context):
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        color = self.get_style_context().get_color(Gtk.StateFlags.NORMAL)
        cr.set_source_rgba(color.red, color.green, color.blue, 0.9)
        gap = 2.0
        bar_width = (width - gap * (self.count - 1)) / self.count
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(bar_width)
        for i, level in enumerate(self._levels()):
            x = i * (bar_width + gap) + bar_width / 2
            half = max(level * height, bar_width) / 2 - bar_width / 2
            cr.move_to(x, height / 2 - half)
            cr.line_to(x, height / 2 + half)
        cr.stroke()


def _rounded_rect(cr: cairo.Context, w: float, h: float, r: float):
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(w - r, r, r, -1.5708, 0)
    cr.arc(w - r, h - r, r, 0, 1.5708)
    cr.arc(r, h - r, r, 1.5708, 3.1416)
    cr.arc(r, r, r, 3.1416, 4.7124)
    cr.close_path()


class ArtThumb(Gtk.DrawingArea):
    """An image cover-fitted into a rounded rectangle (a faint tile without one)."""

    def __init__(self, width: int, height: int, radius: float):
        super().__init__()
        self.set_name("island-art")
        self.set_size_request(width, height)
        self.set_valign(Gtk.Align.CENTER)
        self.radius = radius
        self.pixbuf: GdkPixbuf.Pixbuf | None = None
        self.connect("draw", self._on_draw)
        self.show()

    def set_pixbuf(self, pixbuf: GdkPixbuf.Pixbuf | None):
        self.pixbuf = pixbuf
        self.queue_draw()

    def _on_draw(self, _widget, cr: cairo.Context):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        _rounded_rect(cr, w, h, self.radius)
        if self.pixbuf is None:
            color = self.get_style_context().get_color(Gtk.StateFlags.NORMAL)
            cr.set_source_rgba(color.red, color.green, color.blue, 0.15)
            cr.fill()
            return
        cr.clip()
        pw, ph = self.pixbuf.get_width(), self.pixbuf.get_height()
        scale = max(w / pw, h / ph)
        cr.translate((w - pw * scale) / 2, (h - ph * scale) / 2)
        cr.scale(scale, scale)
        Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, 0, 0)
        cr.paint()


class Swatch(Gtk.DrawingArea):
    """A picked colour, as a rounded square."""

    def __init__(self, size: int = 34):
        super().__init__()
        self.set_size_request(size, size)
        self.set_valign(Gtk.Align.CENTER)
        self.rgba = Gdk.RGBA()
        self.connect("draw", self._on_draw)

    def set_color(self, color: str):
        self.rgba.parse(color)
        self.queue_draw()

    def _on_draw(self, _widget, cr: cairo.Context):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        _rounded_rect(cr, w, h, 9)
        Gdk.cairo_set_source_rgba(cr, self.rgba)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.25)
        cr.set_line_width(1)
        cr.stroke()


class SeekBar(Gtk.DrawingArea):
    """A thin progress bar; click or drag along it to seek."""

    def __init__(self, on_seek: Callable[[float], None]):
        super().__init__()
        self.set_name("island-seek")
        self.set_size_request(-1, 14)
        self.set_hexpand(True)
        self.set_valign(Gtk.Align.CENTER)
        self.fraction = 0.0
        self.on_seek = on_seek
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON1_MOTION_MASK
        )
        self.connect("draw", self._on_draw)
        self.connect("button-press-event", self._seek)
        self.connect("motion-notify-event", self._seek)
        self.show()

    def set_fraction(self, fraction: float):
        self.fraction = min(max(fraction, 0.0), 1.0)
        self.queue_draw()

    def _seek(self, _widget, event) -> bool:
        width = self.get_allocated_width()
        if width > 0 and self.get_sensitive():
            self.set_fraction(event.x / width)
            self.on_seek(self.fraction)
        return True

    def _on_draw(self, _widget, cr: cairo.Context):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        style = self.get_style_context()
        fg = style.get_color(Gtk.StateFlags.NORMAL)
        found, accent = style.lookup_color("accent")
        if not found:
            accent = fg
        line = 4.0
        cr.save()
        cr.translate(0, (h - line) / 2)
        _rounded_rect(cr, w, line, line / 2)
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.15)
        cr.fill()
        if self.fraction > 0:
            _rounded_rect(cr, max(line, w * self.fraction), line, line / 2)
            Gdk.cairo_set_source_rgba(cr, accent)
            cr.fill()
        cr.restore()
        # the playhead
        cr.arc(min(max(w * self.fraction, 5), w - 5), h / 2, 5, 0, 6.2832)
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.95)
        cr.fill()


def _format_time(microseconds: float) -> str:
    seconds = max(0, int(microseconds // 1_000_000))
    return f"{seconds // 60}:{seconds % 60:02}"


# The drop-down panel


@dataclass
class Announcement:
    title: str
    subtitle: str = ""
    icon_name: str | None = None
    color: str | None = None  # a swatch instead of an icon
    image_path: str | None = None  # a thumbnail instead of an icon


class IslandDrop(WaylandWindow):
    def __init__(self, island: "DynamicIsland"):
        self.island = island
        self.media = island.media

        # Media: art, title, artist and controls; progress below
        self.media_art = ArtThumb(56, 56, 12)
        self.media_title = Label(
            "", name="island-title", h_align="start", ellipsization="end",
            max_chars_width=30,
        )  # fmt: skip
        self.media_artist = Label(
            "", name="island-subtitle", h_align="start", ellipsization="end",
            max_chars_width=34,
        )  # fmt: skip
        self.play_icon = Image(icon_name="media-playback-pause-symbolic", icon_size=18)
        self.seek = SeekBar(self.media.seek)
        self.elapsed = Label("0:00", name="island-time", style_classes=["tnum"])
        self.total = Label("0:00", name="island-time", style_classes=["tnum"])
        media = Box(
            name="island-media",
            orientation="v",
            spacing=8,
            children=[
                Box(
                    spacing=12,
                    children=[
                        self.media_art,
                        Box(
                            orientation="v",
                            v_align="center",
                            h_expand=True,
                            children=[self.media_title, self.media_artist],
                        ),
                        Box(
                            spacing=2,
                            v_align="center",
                            children=[
                                self._control(
                                    "media-skip-backward-symbolic", "previous"
                                ),
                                Button(
                                    name="island-control",
                                    child=self.play_icon,
                                    on_clicked=lambda *_: self.media.act("play_pause"),
                                ),
                                self._control("media-skip-forward-symbolic", "next"),
                            ],
                        ),
                    ],
                ),
                Box(spacing=8, children=[self.elapsed, self.seek, self.total]),
            ],
        )

        # Announcement: an icon (or swatch, or thumbnail), a title, a detail
        self.event_icon = Image(name="island-event-icon", icon_size=22)
        self.event_swatch = Swatch()
        self.event_thumb = ArtThumb(64, 40, 7)
        for widget in (self.event_icon, self.event_swatch, self.event_thumb):
            widget.set_no_show_all(True)
        self.event_title = Label("", name="island-title", h_align="start")
        self.event_subtitle = Label(
            "", name="island-subtitle", h_align="start", ellipsization="end",
            max_chars_width=44,
        )  # fmt: skip
        self.event_subtitle.set_no_show_all(True)
        event = Box(
            name="island-event",
            spacing=12,
            children=[
                Box(
                    v_align="center",
                    children=[self.event_icon, self.event_swatch, self.event_thumb],
                ),
                Box(
                    orientation="v",
                    v_align="center",
                    children=[self.event_title, self.event_subtitle],
                ),
            ],
        )

        self.stack = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.CROSSFADE,
            transition_duration=180,
            # sizes follow the pill's widening instead (DynamicIsland._widen)
            interpolate_size=False,
            hhomogeneous=False,
            vhomogeneous=False,
        )
        self.stack.add_named(media, "media")
        self.stack.add_named(event, "event")
        self.stack.show()

        self.body = Box(name="island-drop", children=[self.stack])
        self.revealer = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
            transition_duration=REVEAL_MS,
        )
        self.revealer.add(self.body)
        self.revealer.connect("notify::child-revealed", self._on_revealed)
        self.revealer.show()

        events = Gtk.EventBox()
        # never 0px tall: the compositor doesn't send frames to an empty
        # surface, and the revealer's animation waits on them
        events.set_size_request(-1, 1)
        events.add(self.revealer)
        events.add_events(
            Gdk.EventMask.ENTER_NOTIFY_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
        )
        events.connect("enter-notify-event", lambda *_: island.pointer_entered())
        events.connect("leave-notify-event", self._on_leave)
        events.connect("button-press-event", self._on_press)
        events.show()

        super().__init__(
            # blurred like the other popups (fabric_glass in hyprland.lua)
            title="fabric-popup",
            layer="top",
            # top only: centred, and placed under the bar's exclusive zone
            anchor="top",
            exclusivity="none",
            visible=False,
            child=events,
        )

    def _control(self, icon_name: str, action: str) -> Button:
        return Button(
            name="island-control",
            child=Image(icon_name=icon_name, icon_size=16),
            on_clicked=lambda *_: self.media.act(action),
        )

    def _on_leave(self, _widget, event: Gdk.EventCrossing) -> bool:
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.island.pointer_left()
        return False

    def _on_press(self, _widget, event: Gdk.EventButton) -> bool:
        # buttons and the seek bar handle their own clicks; elsewhere dismisses
        if event.button == 1:
            self.island.dismiss()
        return False

    # Showing

    @property
    def open(self) -> bool:
        return self.revealer.get_reveal_child()

    def natural_width(self, view: str) -> int:
        child = self.stack.get_child_by_name(view)
        if child is None:
            return 0
        _minimum, natural = child.get_preferred_width()
        return natural + DROP_PADDING

    def show_view(self, view: str):
        self.stack.set_visible_child_name(view)
        if not self.get_visible():
            self.show()
        # windows grow with their content but never shrink by themselves
        self.resize(1, 1)
        self.revealer.set_reveal_child(True)

    def close(self):
        self.revealer.set_reveal_child(False)

    def _on_revealed(self, *_):
        # unmapped while closed, so it never catches clicks
        if not self.revealer.get_child_revealed() and not self.open:
            self.hide()

    def set_width(self, width: int):
        self.body.set_size_request(width, -1)

    def show_announcement(self, item: Announcement):
        self.event_title.set_label(item.title)
        self.event_subtitle.set_label(item.subtitle)
        self.event_subtitle.set_visible(bool(item.subtitle))
        self.event_icon.set_visible(False)
        self.event_swatch.set_visible(False)
        self.event_thumb.set_visible(False)
        if item.color:
            self.event_swatch.set_color(item.color)
            self.event_swatch.show()
        elif item.image_path:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    item.image_path, 256, 160, True
                )
            except GLib.Error:
                pixbuf = None
            self.event_thumb.set_pixbuf(pixbuf)
            self.event_thumb.show()
        else:
            self.event_icon.set_from_icon_name(
                item.icon_name or "dialog-information-symbolic", 22
            )
            self.event_icon.show()
        self.show_view("event")

    def update_media(self):
        player = self.media.current_player()
        if player is None:
            return
        self.media_title.set_label(player.title or "Unknown title")
        self.media_artist.set_label(", ".join(player.artist or []) or "Unknown artist")
        playing = player.playback_status == "Playing"
        self.play_icon.set_from_icon_name(
            "media-playback-pause-symbolic"
            if playing
            else "media-playback-start-symbolic",
            18,
        )
        length = player.length or 0
        position = self.media.position
        self.seek.set_fraction(position / length if length else 0)
        self.seek.set_sensitive(bool(length) and player.can_seek)
        self.elapsed.set_label(_format_time(position))
        self.total.set_label(_format_time(length) if length else "--:--")


# The bar's part


class DynamicIsland(Gtk.EventBox):
    def __init__(self, workspaces: Gtk.Widget):
        self.media = get_media_state()
        self.focus = get_focus_timer()
        self.pill: Gtk.Widget | None = None

        # Focus timer chip, while a session runs
        self.focus_label = Label("", name="island-chip-label", style_classes=["tnum"])
        self.focus_chip = Box(
            name="island-chip",
            spacing=5,
            v_align="center",
            children=[
                Image(icon_name="alarm-symbolic", icon_size=14),
                self.focus_label,
            ],
        )
        self.focus_chip.set_no_show_all(True)
        for child in self.focus_chip.children:
            child.show()

        # Now playing chip: hovering it opens the media view
        self.chip_art = ArtThumb(18, 18, 5)
        self.chip_bars = MiniBars()
        chip = Box(
            name="island-chip",
            spacing=6,
            v_align="center",
            children=[self.chip_art, self.chip_bars],
        )
        self.media_chip = Gtk.EventBox(child=chip)
        self.media_chip.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK)
        self.media_chip.connect("enter-notify-event", lambda *_: self._on_chip_enter())
        self.media_chip.set_no_show_all(True)
        chip.show_all()

        # an event box, to know when the pointer leaves for good
        super().__init__(name="island")
        self.add(
            Box(
                v_align="center",
                children=[workspaces, self.focus_chip, self.media_chip],
            )
        )
        self.add_events(
            Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        self.connect("enter-notify-event", lambda *_: self.pointer_entered())
        self.connect("leave-notify-event", self._on_leave)
        # plain GTK widgets start hidden, unlike fabric's
        self.show()

        self.drop = IslandDrop(self)
        self._queue: list[Announcement | str] = []
        self._showing: str | None = None  # "media" or "event" while open
        self._timeout: int | None = None
        self._leave_timeout: int | None = None
        self._position_tick: int | None = None
        self._hovered = False
        self._art_url: str | None = None
        self._track_key: tuple | None = None
        self._width_tick: int | None = None
        self._width = 0.0
        self._width_from = 0.0
        self._width_to = 0.0
        self._width_start = 0
        self._closing_width = False
        self._quiet_until = GLib.get_monotonic_time() / 1e6 + STARTUP_QUIET_S

        self.media.connect("changed", lambda *_: self._on_media_changed())
        self.focus.connect("changed", lambda *_: self._on_focus_changed())
        self._watch_events()
        self._on_media_changed()
        self._on_focus_changed()

    def attach_pill(self, pill: Gtk.Widget):
        """The bar's centre group, which widens and squares off while open."""
        self.pill = pill

    def _on_leave(self, _widget, event: Gdk.EventCrossing) -> bool:
        # moving onto a child (the chip) isn't leaving
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.pointer_left()
        return False

    # Opening and closing

    def _open(self, view: str):
        self._showing = view
        if view == "media":
            self.drop.update_media()
            if self._position_tick is None:
                self._position_tick = GLib.timeout_add(
                    POSITION_TICK_MS, self._tick_position
                )
        else:
            self._stop_position_tick()
        self.drop.show_view(view)
        self._widen(self.drop.natural_width(view))
        if self.pill is not None:
            self.pill.get_style_context().add_class("island-open")

    def _close(self):
        self._showing = None
        self._clear_timeout()
        self._stop_position_tick()
        self.drop.close()
        self._widen(None)

    def dismiss(self):
        """Close now, and drop whatever was waiting."""
        self._queue.clear()
        self._hovered = False
        self._close()

    def _clear_timeout(self):
        if self._timeout is not None:
            GLib.source_remove(self._timeout)
            self._timeout = None

    def _stop_position_tick(self):
        if self._position_tick is not None:
            GLib.source_remove(self._position_tick)
            self._position_tick = None

    def _tick_position(self) -> bool:
        self.drop.update_media()
        return True

    # Widening: the pill and the panel share one width while open

    def _base_width(self) -> int:
        if self.pill is None:
            return 0
        current = self.pill.get_size_request()
        self.pill.set_size_request(-1, -1)
        _minimum, natural = self.pill.get_preferred_width()
        self.pill.set_size_request(*current)
        return natural

    def _widen(self, content_width: int | None):
        if self.pill is None:
            return
        base = self._base_width()
        target = base if content_width is None else max(base, content_width)
        self._width_from = self._width or base
        self._width_to = target
        self._width_start = GLib.get_monotonic_time()
        self._closing_width = content_width is None
        if self._width_tick is None:
            self._width_tick = self.pill.add_tick_callback(self._animate_width)

    def _animate_width(self, _widget, clock: Gdk.FrameClock) -> bool:
        assert self.pill is not None
        t = min(1.0, (clock.get_frame_time() - self._width_start) / 1000 / WIDEN_MS)
        ease = 1 - (1 - t) ** 3
        self._width = self._width_from + (self._width_to - self._width_from) * ease
        width = round(self._width)
        self.pill.set_size_request(width, -1)
        self.drop.set_width(width)
        if t < 1:
            return True
        self._width_tick = None
        if self._closing_width:
            # back to its own size; rounded again once the panel has gone
            self.pill.set_size_request(-1, -1)
            self._width = 0.0
            GLib.timeout_add(REVEAL_MS, self._unsquare)
        return False

    def _unsquare(self) -> bool:
        if self._showing is None and self.pill is not None:
            self.pill.get_style_context().remove_class("island-open")
        return False

    # The queue

    def announce(self, item: Announcement | str):
        """Show an announcement (or "media" for the track) after what's showing."""
        if self._showing is None and not self._hovered:
            self._show(item)
        else:
            self._queue.append(item)

    def show_event(self, icon_name: str, title: str, subtitle: str = ""):
        self.announce(Announcement(title, subtitle, icon_name=icon_name))

    def _show(self, item: Announcement | str):
        self._clear_timeout()
        if isinstance(item, Announcement):
            self.drop.show_announcement(item)
            self._open("event")
            duration = EVENT_MS
        else:
            self._open("media")
            duration = TRACK_MS
        self._timeout = GLib.timeout_add(duration, self._next)

    def _next(self) -> bool:
        self._timeout = None
        if self._hovered:
            # the pointer's on it: keep the media view until it leaves
            if self._showing != "media" and self.media.current_player() is not None:
                self._open("media")
            return False
        if self._queue:
            self._show(self._queue.pop(0))
        else:
            self._close()
        return False

    # Hover

    def _on_chip_enter(self):
        self.pointer_entered()
        if self.media.current_player() is not None:
            self._hovered = True
            self._clear_timeout()
            self._open("media")

    def pointer_entered(self):
        if self._leave_timeout is not None:
            GLib.source_remove(self._leave_timeout)
            self._leave_timeout = None
        if self._showing is not None:
            self._hovered = True

    def pointer_left(self):
        if self._leave_timeout is not None:
            GLib.source_remove(self._leave_timeout)

        def leave():
            self._leave_timeout = None
            if not self._hovered:
                return False
            self._hovered = False
            if self._timeout is None:
                self._next()
            return False

        self._leave_timeout = GLib.timeout_add(LEAVE_DELAY_MS, leave)

    # Chips

    def _on_focus_changed(self):
        running = self.focus.running
        self.focus_chip.set_visible(running)
        if running:
            minutes, seconds = divmod(self.focus.remaining, 60)
            self.focus_label.set_label(f"{minutes}:{seconds:02}")

    def _on_media_changed(self):
        player = self.media.current_player()
        playing = player is not None and player.playback_status == "Playing"
        self.media_chip.set_visible(playing)
        self.chip_bars.set_active(playing)
        if player is None:
            self._track_key = None
            if self._showing == "media":
                self._close()
            return
        if self._showing == "media":
            self.drop.update_media()

        url = player.arturl or None
        if url != self._art_url:
            self._art_url = url
            load_art(url, lambda pixbuf, u=url: self._set_art(u, pixbuf))

        # a new track that's playing gets announced
        key = (player.bus_name, player.title, tuple(player.artist or []))
        if key != self._track_key:
            self._track_key = key
            if self._news() and playing and player.title:
                self.announce("media")

    def _set_art(self, url: str | None, pixbuf: GdkPixbuf.Pixbuf | None):
        if url != self._art_url:
            return
        self.chip_art.set_pixbuf(pixbuf)
        self.drop.media_art.set_pixbuf(pixbuf)

    def _news(self) -> bool:
        return GLib.get_monotonic_time() / 1e6 > self._quiet_until

    # What gets announced

    def _watch_events(self):
        # imported here: the prayer widgets import this package's siblings
        from fabric_config.components.bar.widgets.prayer_times import (
            _get_prayer_service,
        )
        from fabric_config.components.quick_settings.widgets.submenus.bluetooth import (
            read_battery_percentage,
        )

        prayers = _get_prayer_service()

        def prayer_icon(prayer: str) -> str:
            night = prayer in ("Fajr", "Maghrib", "Isha")
            return "weather-clear-night-symbolic" if night else "weather-clear-symbolic"

        prayers.connect(
            "prayer-time",
            lambda _, prayer: self.show_event(
                prayer_icon(prayer), prayer, "It's time to pray"
            ),
        )
        prayers.connect(
            "prayer-soon",
            lambda _, prayer, minutes: self.show_event(
                prayer_icon(prayer), f"{prayer} in {minutes} min", "Time to get ready"
            ),
        )

        config.sc.connect(
            "recording",
            lambda _, recording: self.show_event(
                "media-record-symbolic",
                "Recording" if recording else "Recording saved",
                "Click the red dot to stop"
                if recording
                else "In ~/Videos/Screencasting",
            ),
        )
        config.sc.connect(
            "screenshot-taken",
            lambda _, path: self.announce(
                Announcement(
                    "Screenshot saved" if path else "Screenshot copied",
                    path.replace(GLib.get_home_dir(), "~")
                    if path
                    else "To the clipboard",
                    icon_name="camera-photo-symbolic",
                    image_path=path or None,
                )
            ),
        )
        color_picker.connect(
            "picked",
            lambda _, color: self.announce(
                Announcement(f"Copied {color}", "Picked from the screen", color=color)
            ),
        )
        config.caffeine.connect(
            "notify::active",
            lambda *_: self.show_event(
                "my-caffeine-on-symbolic",
                "Caffeine on" if config.caffeine.active else "Caffeine off",
                "The screen stays awake"
                if config.caffeine.active
                else "The screen can sleep again",
            ),
        )
        config.notifications.connect(
            "notify::dnd",
            lambda *_: self.show_event(
                "notifications-disabled-symbolic"
                if config.notifications.dnd
                else "notification-symbolic",
                "Do Not Disturb" if config.notifications.dnd else "Notifications on",
                "Only critical notifications pop up"
                if config.notifications.dnd
                else "",
            ),
        )

        profile_names = {
            "power-saver": "Power saver",
            "balanced": "Balanced",
            "performance": "Performance",
        }

        def profile_changed(*_):
            profiles = config.power_profiles
            if self._news() and profiles.available:
                self.show_event(
                    f"power-profile-{profiles.profile}-symbolic",
                    profile_names.get(profiles.profile, "Power profile"),
                    "Power profile",
                )

        config.power_profiles.connect("notify::profile", profile_changed)

        self.focus.connect(
            "started",
            lambda _, minutes: self.show_event(
                "alarm-symbolic", f"Focus for {minutes} min", "Stay with it"
            ),
        )
        self.focus.connect(
            "finished",
            lambda _, minutes: self.show_event(
                "alarm-symbolic",
                "Focus session done",
                f"{minutes} minutes. Take a break",
            ),
        )

        # Bluetooth devices connecting and disconnecting
        connected: dict[str, bool] = {}

        def watch_device(address: str):
            device = config.bluetooth_client.get_device(address)
            if device is None:
                return
            connected[address] = device.connected

            def changed(*_):
                was, now = connected.get(address, False), device.connected
                connected[address] = now
                if was == now or not self._news():
                    return
                if now:
                    battery = read_battery_percentage(device, None)
                    self.show_event(
                        device.icon_name or "bluetooth-active-symbolic",
                        f"{device.name} connected",
                        f"Battery {battery}%" if battery > 0 else "Bluetooth",
                    )
                else:
                    self.show_event(
                        "bluetooth-disabled-symbolic",
                        f"{device.name} disconnected",
                        "Bluetooth",
                    )

            device.connect("changed", changed)

        config.bluetooth_client.connect(
            "device-added", lambda _, address: watch_device(address)
        )
        for device in config.bluetooth_client.devices:
            watch_device(device.address)

        # Wi-Fi joining and dropping a network
        wifi = config.network.get_wifi()
        if wifi is not None:
            last_ssid = [wifi.get_ssid()]

            def ssid_changed(*_):
                ssid = wifi.get_ssid()
                previous, last_ssid[0] = last_ssid[0], ssid
                if ssid == previous or not self._news():
                    return
                if ssid:
                    self.show_event(
                        "network-wireless-symbolic", f"Connected to {ssid}", "Wi-Fi"
                    )
                elif previous:
                    self.show_event(
                        "network-wireless-offline-symbolic",
                        "Wi-Fi disconnected",
                        f"Left {previous}",
                    )

            wifi.connect("notify::ssid", ssid_changed)
