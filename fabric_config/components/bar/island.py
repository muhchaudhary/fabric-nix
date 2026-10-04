"""
The bar's centre as a "dynamic island": normally the workspaces (plus a small
now-playing chip while music plays), it grows to show what just happened (a
new track, recording started, caffeine on, ...) and shrinks back after a few
seconds. Hovering it while something is playing opens the media view, with
the current lyric line when the track has synced lyrics.

It's a Gtk.Stack with `interpolate_size`, so the pill animates its width
between views. Every view has the bar's height (`vhomogeneous`): the bar
reserves space by its height, and a growing bar would push windows around.
"""

from collections.abc import Sequence

import cairo
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

import fabric_config.config as config
from fabric_config.components.desktop.media import get_media_state
from fabric_config.components.desktop.music_player import load_art

EVENT_MS = 3500
TRACK_MS = 4500
# leaving the pill closes the media view after this; brushing past doesn't
LEAVE_DELAY_MS = 350
LYRIC_TICK_MS = 300
TRANSITION_MS = 280
# players turn up just after startup; what's already playing isn't news
STARTUP_QUIET_S = 6


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


class ArtThumb(Gtk.DrawingArea):
    """Album art as a small rounded square (a note icon's place without art)."""

    def __init__(self, size: int, radius: float):
        super().__init__()
        self.set_name("island-art")
        self.set_size_request(size, size)
        self.set_valign(Gtk.Align.CENTER)
        self.size = size
        self.radius = radius
        self.pixbuf: GdkPixbuf.Pixbuf | None = None
        self.connect("draw", self._on_draw)
        self.show()

    def set_pixbuf(self, pixbuf: GdkPixbuf.Pixbuf | None):
        self.pixbuf = pixbuf
        self.queue_draw()

    def _on_draw(self, _widget, cr: cairo.Context):
        size, r = self.size, self.radius
        cr.new_sub_path()
        cr.arc(size - r, r, r, -1.5708, 0)
        cr.arc(size - r, size - r, r, 0, 1.5708)
        cr.arc(r, size - r, r, 1.5708, 3.1416)
        cr.arc(r, r, r, 3.1416, 4.7124)
        cr.close_path()
        if self.pixbuf is None:
            color = self.get_style_context().get_color(Gtk.StateFlags.NORMAL)
            cr.set_source_rgba(color.red, color.green, color.blue, 0.15)
            cr.fill()
            return
        cr.clip()
        # cover-fit the art into the square
        w, h = self.pixbuf.get_width(), self.pixbuf.get_height()
        scale = size / min(w, h)
        cr.translate((size - w * scale) / 2, (size - h * scale) / 2)
        cr.scale(scale, scale)
        Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, 0, 0)
        cr.paint()


class DynamicIsland(Gtk.EventBox):
    def __init__(self, workspaces: Gtk.Widget):
        super().__init__(name="island")
        self.media = get_media_state()
        self._timeout: int | None = None
        self._leave_timeout: int | None = None
        self._lyric_tick: int | None = None
        self._hovered = False
        self._art_url: str | None = None
        self._track_key: tuple | None = None
        self._artist = ""
        self._quiet_until = GLib.get_monotonic_time() / 1e6 + STARTUP_QUIET_S

        # Idle: workspaces, and a now-playing chip while music plays
        self.chip_art = ArtThumb(18, 5)
        self.chip_bars = MiniBars()
        self.chip = Box(
            name="island-chip",
            spacing=6,
            v_align="center",
            children=[self.chip_art, self.chip_bars],
        )
        # hovering the chip (not the workspaces, which stay clickable) opens
        # the media view
        self.chip_events = Gtk.EventBox(child=self.chip)
        self.chip_events.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK)
        self.chip_events.connect("enter-notify-event", self._on_chip_enter)
        self.chip_events.set_no_show_all(True)
        idle = Box(children=[workspaces, self.chip_events], v_align="center")

        # Media: art, title and artist (or the lyric), controls
        self.media_art = ArtThumb(28, 7)
        self.media_title = Label(
            "", name="island-title", h_align="start", ellipsization="end",
            max_chars_width=34,
        )  # fmt: skip
        self.media_subtitle = Label(
            "", name="island-subtitle", h_align="start", ellipsization="end",
            max_chars_width=40,
        )  # fmt: skip
        self.play_icon = Image(icon_name="media-playback-pause-symbolic", icon_size=16)
        media = Box(
            name="island-media",
            spacing=10,
            v_align="center",
            children=[
                self.media_art,
                Box(
                    orientation="v",
                    v_align="center",
                    h_expand=True,
                    children=[self.media_title, self.media_subtitle],
                ),
                self._control("media-skip-backward-symbolic", "previous"),
                Button(
                    name="island-control",
                    child=self.play_icon,
                    on_clicked=lambda *_: self.media.act("play_pause"),
                ),
                self._control("media-skip-forward-symbolic", "next"),
            ],
        )

        # Event: an icon, a title and a detail line
        self.event_icon = Image(name="island-event-icon", icon_size=18)
        self.event_title = Label("", name="island-title", h_align="start")
        self.event_subtitle = Label(
            "", name="island-subtitle", h_align="start", ellipsization="end",
            max_chars_width=40,
        )  # fmt: skip
        event = Box(
            name="island-event",
            spacing=10,
            v_align="center",
            children=[
                self.event_icon,
                Box(
                    orientation="v",
                    v_align="center",
                    children=[self.event_title, self.event_subtitle],
                ),
            ],
        )

        self.stack = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.CROSSFADE,
            transition_duration=TRANSITION_MS,
            interpolate_size=True,
            hhomogeneous=False,
            vhomogeneous=True,
        )
        self.stack.add_named(idle, "idle")
        self.stack.add_named(media, "media")
        self.stack.add_named(event, "event")
        self.stack.show()
        self.add(self.stack)
        # plain GTK widgets start hidden, unlike fabric's
        self.show()

        self.add_events(
            Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        self.connect("enter-notify-event", self._on_enter)
        self.connect("leave-notify-event", self._on_leave)

        self.media.connect("changed", lambda *_: self._on_media_changed())
        self._watch_events()
        self._on_media_changed()

    def _control(self, icon_name: str, action: str) -> Button:
        return Button(
            name="island-control",
            child=Image(icon_name=icon_name, icon_size=16),
            on_clicked=lambda *_: self.media.act(action),
        )

    # Views

    def _set_view(self, name: str):
        if self.stack.get_visible_child_name() == name:
            return
        self.stack.set_visible_child_name(name)
        if name == "media":
            self._start_lyrics()
        else:
            self._stop_lyrics()
        for view in ("media", "event"):
            if name == view:
                self.get_style_context().add_class(view)
            else:
                self.get_style_context().remove_class(view)

    def _rest_view(self) -> str:
        """What to show when nothing is being announced."""
        if self._hovered and self.media.current_player() is not None:
            return "media"
        return "idle"

    def _settle(self):
        self._clear_timeout()
        self._set_view(self._rest_view())

    def _clear_timeout(self):
        if self._timeout is not None:
            GLib.source_remove(self._timeout)
            self._timeout = None

    def _show_for(self, view: str, duration_ms: int):
        self._clear_timeout()
        self._set_view(view)

        def done():
            self._timeout = None
            self._set_view(self._rest_view())
            return False

        self._timeout = GLib.timeout_add(duration_ms, done)

    def show_event(self, icon_name: str, title: str, subtitle: str = ""):
        """Grow to announce something, then shrink back."""
        self.event_icon.set_from_icon_name(icon_name, 18)
        self.event_title.set_label(title)
        self.event_subtitle.set_label(subtitle)
        self.event_subtitle.set_visible(bool(subtitle))
        self._show_for("event", EVENT_MS)

    # Hover

    def _on_enter(self, _widget, _event: Gdk.EventCrossing):
        if self._leave_timeout is not None:
            GLib.source_remove(self._leave_timeout)
            self._leave_timeout = None
        return False

    def _on_chip_enter(self, _widget, _event: Gdk.EventCrossing):
        self._hovered = True
        if self.media.current_player() is not None:
            # hovering takes over from an announcement
            self._clear_timeout()
            self._set_view("media")
        return False

    def _on_leave(self, _widget, event: Gdk.EventCrossing):
        # moving onto a child button isn't leaving
        if event.detail == Gdk.NotifyType.INFERIOR:
            return False
        if self._leave_timeout is not None:
            GLib.source_remove(self._leave_timeout)

        def leave():
            self._leave_timeout = None
            self._hovered = False
            if self._timeout is None:
                self._set_view("idle")
            return False

        self._leave_timeout = GLib.timeout_add(LEAVE_DELAY_MS, leave)
        return False

    # Media

    def _on_media_changed(self):
        player = self.media.current_player()
        playing = player is not None and player.playback_status == "Playing"
        self.chip_events.set_visible(playing)
        self.chip.show()
        self.chip_bars.set_active(playing)
        self.play_icon.set_from_icon_name(
            "media-playback-pause-symbolic"
            if playing
            else "media-playback-start-symbolic",
            16,
        )
        if player is None:
            self._track_key = None
            if self.stack.get_visible_child_name() == "media":
                self._settle()
            return

        artists = ", ".join(player.artist or [])
        self.media_title.set_label(player.title or "Unknown title")
        self._artist = artists
        self._update_subtitle()

        url = player.arturl or None
        if url != self._art_url:
            self._art_url = url
            load_art(url, lambda pixbuf, u=url: self._set_art(u, pixbuf))

        # a new track that's playing gets announced
        key = (player.bus_name, player.title, artists)
        if key != self._track_key:
            self._track_key = key
            news = GLib.get_monotonic_time() / 1e6 > self._quiet_until
            if news and playing and player.title and self._timeout is None:
                self._show_for("media", TRACK_MS)

    def _set_art(self, url: str | None, pixbuf: GdkPixbuf.Pixbuf | None):
        if url != self._art_url:
            return
        self.chip_art.set_pixbuf(pixbuf)
        self.media_art.set_pixbuf(pixbuf)

    def _update_subtitle(self) -> bool:
        lines: Sequence[str] | None = (
            self.media.lyric_lines() if self.media.lyrics else None
        )
        lyric = lines[0] if lines else ""
        self.media_subtitle.set_label(f"♪ {lyric}" if lyric else self._artist)
        return True

    def _start_lyrics(self):
        if self._lyric_tick is None:
            self._lyric_tick = GLib.timeout_add(LYRIC_TICK_MS, self._update_subtitle)

    def _stop_lyrics(self):
        if self._lyric_tick is not None:
            GLib.source_remove(self._lyric_tick)
            self._lyric_tick = None

    # What gets announced

    def _watch_events(self):
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
