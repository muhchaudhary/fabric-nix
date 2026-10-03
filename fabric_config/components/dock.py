import json
import queue
import threading
from collections.abc import Callable

import cairo
import gi
from fabric import Application
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow as Window
from hyprland_toplevel_streamer import Frame, HyprlandFrameCapture
from loguru import logger

from fabric_config.utils.hyprland_monitor import get_hyprland_monitors
from fabric_config.utils.icon_resolver import get_icon_resolver
from fabric_config.widgets.rounded_cover_image import RoundedCoverImage

gi.require_version("Glace", "0.1")
from gi.repository import Gdk, GdkPixbuf, Glace, GLib, Gtk  # noqa: E402

ICON_SIZE = 44
MAX_DOTS = 3
# the strip along the screen edge that reveals the hidden dock
HOT_ZONE = 3
REVEAL_DELAY_MS = 120
HIDE_DELAY_MS = 400
# rest on an icon this long before its preview opens; once one is open,
# moving to another icon switches almost at once
PREVIEW_DELAY_MS = 350
PREVIEW_SWITCH_MS = 60
PREVIEW_HIDE_MS = 250
THUMB_HEIGHT = 120
THUMB_MIN_WIDTH = 100
THUMB_MAX_WIDTH = 240
# room for the dock plus the tallest preview. The window never resizes: when a
# bottom-anchored layer surface grows, its input region (in top-left surface
# coordinates) lags a frame behind and the pointer seems to leave the dock
WINDOW_HEIGHT = THUMB_HEIGHT + 200


def hyprland_clients() -> list[dict]:
    try:
        clients = json.loads(get_hyprland_monitors().send_command("j/clients").reply)
    except Exception as e:
        logger.error(f"[Dock] fetching Hyprland clients failed: {e}")
        return []
    return [c for c in clients if c.get("mapped", True)]


def focus_window(address: str):
    # Hyprland 0.56+ (Lua config) rejects the old "focuswindow address:..." form
    get_hyprland_monitors().send_command(
        f"/dispatch hl.dsp.focus({{ window = 'address:{address}' }})"
    )


def close_window(address: str):
    get_hyprland_monitors().send_command(
        f"/dispatch hl.dsp.window.close({{ window = 'address:{address}' }})"
    )


def frame_to_thumbnail(frame: Frame, width: int, height: int) -> GdkPixbuf.Pixbuf:
    """
    Cover-fit a BGRA frame into width x height and return it as RGBA.

    The capture library's own RGBA conversion holds the GIL for ~50 ms on a
    1440p window (which freezes the GTK loop), so frames are captured as BGRA
    and the channels swapped here, after downscaling, when there are few
    pixels left.
    """
    full = GdkPixbuf.Pixbuf.new_from_bytes(
        GLib.Bytes.new(frame.data),
        GdkPixbuf.Colorspace.RGB,
        True,  # has_alpha
        8,  # bits per sample
        frame.width,
        frame.height,
        frame.rowstride,
    )
    factor = max(width / frame.width, height / frame.height)
    scaled_w = max(width, round(frame.width * factor))
    scaled_h = max(height, round(frame.height * factor))
    scaled = full.scale_simple(scaled_w, scaled_h, GdkPixbuf.InterpType.BILINEAR)
    if scaled is None:
        raise MemoryError("scaling the frame failed")
    cropped = scaled.new_subpixbuf(
        (scaled_w - width) // 2, (scaled_h - height) // 2, width, height
    ).copy()
    if cropped is None:
        raise MemoryError("copying the thumbnail failed")

    rowstride = cropped.get_rowstride()
    pixels = bytearray(cropped.get_pixels())
    if rowstride == width * 4:
        pixels[0::4], pixels[2::4] = pixels[2::4], pixels[0::4]
    else:
        for row in range(height):
            start, end = row * rowstride, row * rowstride + width * 4
            line = pixels[start:end]
            line[0::4], line[2::4] = line[2::4], line[0::4]
            pixels[start:end] = line
    return GdkPixbuf.Pixbuf.new_from_bytes(
        GLib.Bytes.new(bytes(pixels)),
        GdkPixbuf.Colorspace.RGB,
        True,
        8,
        width,
        height,
        rowstride,
    )


class ThumbnailCapturer:
    """
    Captures window thumbnails on a worker thread.

    HyprlandFrameCapture is `unsendable` (it must stay on the thread that made
    it), so the worker owns its own instance. Results come back on the GTK
    thread through GLib.idle_add. Requests from an older generation (the
    pointer has moved to another app) are skipped.
    """

    def __init__(self):
        self.generation = 0
        self._queue: queue.SimpleQueue[
            tuple[int, str, int, int, Callable[[str, GdkPixbuf.Pixbuf], None]]
        ] = queue.SimpleQueue()
        self._thread: threading.Thread | None = None

    def next_generation(self) -> int:
        self.generation += 1
        return self.generation

    def request(
        self,
        address: str,
        width: int,
        height: int,
        callback: Callable[[str, GdkPixbuf.Pixbuf], None],
    ):
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._run, name="dock-thumbnails", daemon=True
            )
            self._thread.start()
        self._queue.put((self.generation, address, width, height, callback))

    def _run(self):
        capture = HyprlandFrameCapture()
        while True:
            generation, address, width, height, callback = self._queue.get()
            if generation != self.generation:
                continue
            try:
                frame = capture.capture(
                    int(address, 16), overlay_cursor=False, rgba=False
                )
                thumbnail = frame_to_thumbnail(frame, width, height)
            except Exception as e:
                logger.warning(f"[Dock] capturing {address} failed: {e}")
                continue

            def deliver(generation=generation, address=address, thumb=thumbnail):
                if generation == self.generation:
                    callback(address, thumb)
                return False

            GLib.idle_add(deliver)


class AppButton(Button):
    """One dock icon per app, with a dot for each of its windows (up to 3)."""

    def __init__(self, app_id: str, dock: "AppBar"):
        self.app_id = app_id
        self.clients: list[Glace.Client] = []
        self._icon = Image(name="dock-app-icon")
        self._dots = Box(name="dock-app-dots", spacing=3, h_align="center")
        super().__init__(
            name="dock-app",
            child=Box(
                orientation="v",
                spacing=2,
                children=[self._icon, self._dots],
            ),
            on_clicked=lambda *_: dock.activate_app(self),
            on_enter_notify_event=lambda *_: dock.schedule_preview(self),
            on_leave_notify_event=lambda *_: dock.schedule_preview_hide(),
        )
        self.connect("notify::scale-factor", lambda *_: self._load_icon())
        self._load_icon()

    def _load_icon(self):
        scale = self.get_scale_factor()
        pixbuf = get_icon_resolver().get_icon_pixbuf(self.app_id, ICON_SIZE * scale)
        if pixbuf is None:
            return
        # a scaled surface keeps the icon sharp on HiDPI monitors
        self._icon.set_from_surface(
            Gdk.cairo_surface_create_from_pixbuf(pixbuf, scale, None)
        )

    def set_clients(self, clients: list[Glace.Client]):
        self.clients = clients
        count = min(len(clients), MAX_DOTS)
        if len(self._dots.children) != count:
            self._dots.children = [Box(name="dock-app-dot") for _ in range(count)]

        if any(c.get_activated() for c in clients):
            self.add_style_class("active")
        else:
            self.remove_style_class("active")

        titles = [c.get_title() for c in clients if c.get_title()]
        self.set_tooltip_text(titles[0] if len(titles) == 1 else None)


class WindowThumbnail(EventBox):
    def __init__(
        self,
        client: dict,
        width: int,
        height: int,
        on_activate: Callable[[str], None],
        on_close: Callable[[str], None],
    ):
        self.address: str = client["address"]
        self.image = RoundedCoverImage(width, height, radius=10)
        title = Label(
            label=client.get("title") or client.get("class", ""),
            name="dock-preview-title",
            ellipsization="end",
            h_expand=True,
        )
        # let the width come from the thumbnail, not the title
        title.set_max_width_chars(1)
        title.set_xalign(0)
        super().__init__(
            name="dock-preview-window",
            style_classes=["clickable"],
            events=["button-press", "enter-notify", "leave-notify"],
            child=Box(
                orientation="v",
                spacing=6,
                children=[
                    Box(
                        spacing=6,
                        children=[
                            title,
                            Button(
                                name="dock-preview-close",
                                image=Image(
                                    icon_name="window-close-symbolic", icon_size=12
                                ),
                                tooltip_text="Close window",
                                on_clicked=lambda *_: on_close(self.address),
                            ),
                        ],
                    ),
                    self.image,
                ],
            ),
            on_button_press_event=lambda _, event: (
                on_activate(self.address) if event.button == 1 else None
            ),
            on_enter_notify_event=lambda *_: self.add_style_class("hover"),
            on_leave_notify_event=lambda _, event: (
                self.remove_style_class("hover")
                if event.detail != Gdk.NotifyType.INFERIOR
                else None
            ),
        )


class AppBar(Box):
    """The dock's icon row: app launcher, then one AppButton per running app."""

    def __init__(self, dock: "AppDock"):
        self._dock = dock
        self._apps: dict[str, AppButton] = {}
        self._clients: list[Glace.Client] = []
        self._sync_id: int | None = None

        self._apps_box = Box(name="dock-apps", spacing=4)
        self._separator = Box(name="dock-separator", v_expand=True)
        super().__init__(
            name="dock",
            spacing=4,
            children=[
                Button(
                    name="dock-launcher",
                    image=Image(icon_name="view-app-grid-symbolic", icon_size=28),
                    tooltip_text="Applications",
                    on_clicked=lambda *_: dock.open_app_menu(),
                    on_enter_notify_event=lambda *_: dock.schedule_preview_hide(),
                ),
                self._separator,
                self._apps_box,
            ],
        )

        self._manager = Glace.Manager()
        self._manager.connect("client-added", self._on_client_added)

    def activate_app(self, button: AppButton):
        self._dock.hide_preview()
        windows = sorted(
            (c for c in hyprland_clients() if c.get("class") == button.app_id),
            key=lambda c: c.get("focusHistoryID", 0),
        )
        if not windows:
            if button.clients:
                button.clients[0].activate()
            return
        # cycle: when this app already has focus, go to its least recent window
        focused = windows[0].get("focusHistoryID") == 0
        target = windows[-1] if focused and len(windows) > 1 else windows[0]
        focus_window(target["address"])

    def schedule_preview(self, button: AppButton):
        self._dock.schedule_preview(button)

    def schedule_preview_hide(self):
        self._dock.schedule_preview_hide()

    def _on_client_added(self, _, client: Glace.Client):
        self._clients.append(client)
        for prop in ("app-id", "activated", "title"):
            client.connect(f"notify::{prop}", lambda *_: self._queue_sync())
        client.connect("close", lambda *_: self._on_client_closed(client))
        self._queue_sync()

    def _on_client_closed(self, client: Glace.Client):
        if client in self._clients:
            self._clients.remove(client)
        self._queue_sync()

    def _queue_sync(self):
        # clients change several properties at once; regroup once per batch
        if self._sync_id is None:
            self._sync_id = GLib.idle_add(self._sync)

    def _sync(self):
        self._sync_id = None
        groups: dict[str, list[Glace.Client]] = {}
        for client in self._clients:
            if app_id := client.get_app_id():
                groups.setdefault(app_id, []).append(client)

        for app_id in [a for a in self._apps if a not in groups]:
            self._apps.pop(app_id).destroy()
        for app_id, clients in groups.items():
            if app_id not in self._apps:
                self._apps[app_id] = AppButton(app_id, self)
                self._apps_box.add(self._apps[app_id])
            self._apps[app_id].set_clients(clients)

        self._separator.set_visible(bool(self._apps))
        self._dock.on_apps_changed()
        return False


class AppDock(Window):
    """
    An auto-hiding dock along the bottom of the screen.

    The window spans the monitor's width so window previews can sit above any
    icon, but its input region only covers what is showing: the dock, the open
    preview, and a thin strip along the screen edge that reveals the dock. The
    rest lets clicks through to the windows below. Keeping the preview in the
    same window means moving between the icons and the preview never leaves
    it, so the dock doesn't hide underneath the pointer. The window keeps a
    fixed height (see WINDOW_HEIGHT); only the revealers inside it move.
    """

    def __init__(self):
        super().__init__(
            name="dock-window",
            layer="top",
            anchor="left bottom right",
            exclusivity="none",
        )
        self._hovered = False
        self._reveal_id: int | None = None
        self._hide_id: int | None = None
        self._preview_id: int | None = None
        self._preview_hide_id: int | None = None
        self._preview_button: AppButton | None = None
        self._preview_tick_id: int | None = None
        self._thumbnails: dict[str, GdkPixbuf.Pixbuf] = {}
        self._thumbnail_widgets: dict[str, WindowThumbnail] = {}
        self._capturer = ThumbnailCapturer()

        self.app_bar = AppBar(self)
        self.dock_revealer = Revealer(
            child=Box(name="dock-container", children=self.app_bar),
            transition_type="slide-up",
            transition_duration=250,
            h_align="center",
        )

        self._preview_thumbs = Box(spacing=8)
        self._preview_card = EventBox(
            name="dock-preview",
            events=["enter-notify", "leave-notify"],
            child=self._preview_thumbs,
            on_enter_notify_event=lambda *_: self._keep_preview(),
            on_leave_notify_event=lambda _, event: (
                self.schedule_preview_hide()
                if event.detail != Gdk.NotifyType.INFERIOR
                else None
            ),
        )
        self._preview_fixed = Gtk.Fixed(hexpand=True)
        self._preview_fixed.put(self._preview_card, 0, 0)
        self.preview_revealer = Revealer(
            child=self._preview_fixed,
            transition_type="slide-up",
            transition_duration=180,
        )

        self.children = EventBox(
            events=["enter-notify", "leave-notify"],
            size=(-1, WINDOW_HEIGHT),
            child=Box(
                orientation="v",
                v_align="end",
                children=[
                    self.preview_revealer,
                    self.dock_revealer,
                    Box(style=f"min-height: {HOT_ZONE}px;"),
                ],
            ),
            on_enter_notify_event=self._on_enter,
            on_leave_notify_event=self._on_leave,
        )

        # the revealers are reallocated on every frame of their animations
        for widget in (self, self.dock_revealer, self.preview_revealer):
            widget.connect("size-allocate", lambda *_: self._update_input_region())
        for revealer in (self.dock_revealer, self.preview_revealer):
            revealer.connect(
                "notify::child-revealed", lambda *_: self._update_input_region()
            )
        self.show_all()

    # region: showing and hiding

    def _on_enter(self, _, event: Gdk.EventCrossing):
        if event.detail == Gdk.NotifyType.INFERIOR:
            return
        self._hovered = True
        self._cancel("_hide_id")
        if not self.dock_revealer.get_reveal_child() and self._reveal_id is None:
            # a short delay so merely brushing the screen edge doesn't pop it up
            self._reveal_id = GLib.timeout_add(REVEAL_DELAY_MS, self._reveal)

    def _on_leave(self, _, event: Gdk.EventCrossing):
        # entering a child (a button) is reported as leaving the event box
        if event.detail == Gdk.NotifyType.INFERIOR:
            return
        self._hovered = False
        self._cancel("_reveal_id")
        if self._hide_id is None:
            self._hide_id = GLib.timeout_add(HIDE_DELAY_MS, self._hide)

    def _reveal(self):
        self._reveal_id = None
        self.dock_revealer.set_reveal_child(True)
        self._update_input_region()
        return False

    def _hide(self):
        self._hide_id = None
        if self._hovered:
            return False
        self.hide_preview()
        self.dock_revealer.set_reveal_child(False)
        return False

    def _cancel(self, attr: str):
        if (source_id := getattr(self, attr)) is not None:
            GLib.source_remove(source_id)
            setattr(self, attr, None)

    def open_app_menu(self):
        self.hide_preview()
        app = self.get_application()
        if isinstance(app, Application):
            app.actions["toggle-appmenu"][0]()

    def on_apps_changed(self):
        # an app closed while its preview was open
        if self._preview_button is not None and (
            self._preview_button.get_parent() is None
        ):
            self.hide_preview()

    # region: window previews

    def schedule_preview(self, button: AppButton):
        self._cancel("_preview_hide_id")
        self._cancel("_preview_id")
        if button is self._preview_button and self.preview_revealer.get_reveal_child():
            return
        delay = (
            PREVIEW_SWITCH_MS
            if self.preview_revealer.get_reveal_child()
            else PREVIEW_DELAY_MS
        )
        self._preview_id = GLib.timeout_add(delay, self._show_preview, button)

    def schedule_preview_hide(self):
        self._cancel("_preview_id")
        if self._preview_hide_id is None and self.preview_revealer.get_reveal_child():
            self._preview_hide_id = GLib.timeout_add(PREVIEW_HIDE_MS, self.hide_preview)

    def hide_preview(self):
        self._cancel("_preview_id")
        self._cancel("_preview_hide_id")
        self._preview_button = None
        self._capturer.next_generation()
        self.preview_revealer.set_reveal_child(False)
        return False

    def _show_preview(self, button: AppButton):
        self._preview_id = None
        clients = hyprland_clients()
        windows = [c for c in clients if c.get("class") == button.app_id]
        if not windows:
            self.hide_preview()
            return False

        # forget thumbnails of windows that are gone
        alive = {c["address"] for c in clients}
        for address in [a for a in self._thumbnails if a not in alive]:
            del self._thumbnails[address]

        was_open = self.preview_revealer.get_reveal_child()
        self._preview_button = button
        self._capturer.next_generation()

        # shrink thumbnails to fit when an app has many windows
        width_available = self.get_allocated_width() - 64
        sizes = [self._thumbnail_size(c) for c in windows]
        total = sum(w for w, _ in sizes) + 20 * len(sizes)
        shrink = min(1.0, width_available / total) if total > 0 else 1.0
        sizes = [(max(40, round(w * shrink)), round(h * shrink)) for w, h in sizes]

        scale = self.get_scale_factor()
        self._thumbnail_widgets = {}
        thumbs = []
        for client, (width, height) in zip(windows, sizes):
            thumb = WindowThumbnail(
                client,
                width,
                height,
                on_activate=self._activate_window,
                on_close=self._close_window,
            )
            # show the last capture straight away, then refresh it
            if (cached := self._thumbnails.get(thumb.address)) is not None:
                thumb.image.set_pixbuf(cached)
            self._capturer.request(
                thumb.address, width * scale, height * scale, self._on_thumbnail
            )
            self._thumbnail_widgets[thumb.address] = thumb
            thumbs.append(thumb)

        self._preview_thumbs.children = thumbs
        self._preview_card.show_all()
        self._place_preview(animate=was_open)
        self.preview_revealer.set_reveal_child(True)
        return False

    def _thumbnail_size(self, client: dict) -> tuple[int, int]:
        width, height = client.get("size") or (16, 9)
        aspect = width / height if height else 16 / 9
        return (
            round(min(THUMB_MAX_WIDTH, max(THUMB_MIN_WIDTH, THUMB_HEIGHT * aspect))),
            THUMB_HEIGHT,
        )

    def _on_thumbnail(self, address: str, pixbuf: GdkPixbuf.Pixbuf):
        self._thumbnails[address] = pixbuf
        if (thumb := self._thumbnail_widgets.get(address)) is not None:
            thumb.image.set_pixbuf(pixbuf)

    def _keep_preview(self):
        self._cancel("_preview_hide_id")
        self._cancel("_preview_id")

    def _activate_window(self, address: str):
        self.hide_preview()
        focus_window(address)

    def _close_window(self, address: str):
        close_window(address)
        button = self._preview_button
        # refresh once Hyprland has closed it
        if button is not None:
            self._cancel("_preview_id")
            self._preview_id = GLib.timeout_add(250, self._show_preview, button)

    def _preview_target_x(self) -> int | None:
        button = self._preview_button
        if button is None or button.get_window() is None:
            return None
        coords = button.translate_coordinates(
            self, button.get_allocated_width() // 2, 0
        )
        if coords is None:
            return None
        card_width = self._preview_card.get_preferred_width()[1]
        x = coords[0] - card_width // 2
        return max(8, min(x, self.get_allocated_width() - card_width - 8))

    def _place_preview(self, animate: bool):
        target = self._preview_target_x()
        if target is None:
            return
        if self._preview_tick_id is not None:
            self._preview_fixed.remove_tick_callback(self._preview_tick_id)
            self._preview_tick_id = None

        start = self._preview_fixed.child_get_property(self._preview_card, "x")
        if not animate or start == target:
            if start != target:
                self._preview_fixed.move(self._preview_card, target, 0)
            return

        begin = GLib.get_monotonic_time()
        duration = 160_000

        def tick(_widget, _clock):
            t = min((GLib.get_monotonic_time() - begin) / duration, 1.0)
            ease = 1 - (1 - t) ** 3
            self._preview_fixed.move(
                self._preview_card, round(start + (target - start) * ease), 0
            )
            if t >= 1.0:
                self._preview_tick_id = None
                return False
            return True

        self._preview_tick_id = self._preview_fixed.add_tick_callback(tick)

    # region: input region

    def _rect_of(self, widget: Gtk.Widget) -> cairo.RectangleInt | None:
        if not widget.get_mapped():
            return None
        coords = widget.translate_coordinates(self, 0, 0)
        width, height = widget.get_allocated_width(), widget.get_allocated_height()
        if coords is None or width <= 1 or height <= 1:
            return None
        return cairo.RectangleInt(coords[0], coords[1], width, height)

    def _update_input_region(self):
        if self.get_window() is None:
            return
        region = cairo.Region()
        dock = self._rect_of(self.dock_revealer)
        if dock is not None:
            region.union(dock)
        # the reveal strip, as wide as the dock (its width is kept when hidden)
        width = self.dock_revealer.get_allocated_width()
        x = (self.get_allocated_width() - width) // 2
        region.union(
            cairo.RectangleInt(
                x, self.get_allocated_height() - HOT_ZONE, width, HOT_ZONE
            )
        )
        if self.preview_revealer.get_reveal_child() or (
            self.preview_revealer.get_child_revealed()
        ):
            if (card := self._rect_of(self._preview_card)) is not None:
                region.union(card)
                # bridge the gap down to the dock so crossing it keeps hover
                if dock is not None:
                    top = card.y + card.height
                    region.union(
                        cairo.RectangleInt(
                            card.x, top, card.width, max(0, dock.y - top + 1)
                        )
                    )
        self.input_shape_combine_region(region)
