import json

import cairo
import gi
from fabric.hyprland.service import Hyprland
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from loguru import logger

import fabric_config.config as config
from fabric_config.services.window_previews import cover_size
from fabric_config.utils.icon_resolver import get_icon_resolver
from fabric_config.utils.wallpaper import (
    query_active_wallpapers,
    wallpaper_for_monitor,
)
from fabric_config.widgets.popup_window_v2 import PopupWindow
from fabric_config.widgets.rounded_cover_image import RoundedCoverImage

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

icon_resolver = get_icon_resolver()
connection = Hyprland()
# Every workspace preview is this tall; its width follows the aspect ratio of
# the monitor the workspace is on, and its windows are scaled to match. This
# keeps previews consistent when monitors differ in size, scale or rotation.
PREVIEW_HEIGHT = 216
CARD_RADIUS = 14
WINDOW_RADIUS = 8
WORKSPACES = range(1, 9)
COLUMNS = 4
# live window previews; a window that doesn't redraw isn't captured
PREVIEW_FPS = 12


# Hyprland 0.56+ (Lua config) only accepts hl.dsp.* dispatches. Always pass an
# explicit `window`: without one, window dispatchers act on the focused window.
def move_window_to_workspace(address: str, workspace_id: int):
    if not address.startswith("0x"):
        logger.error(f"[Overview] Ignoring drop with unexpected data: {address!r}")
        return
    connection.send_command(
        "/dispatch hl.dsp.window.move({ "
        f"workspace = {workspace_id}, window = 'address:{address}', follow = false"
        " })"
    )


# Credit to Aylur for the drag and drop code
TARGET = [Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)]


# Credit to Aylur for the createSurfaceFromWidget code
def createSurfaceFromWidget(widget: Gtk.Widget) -> cairo.ImageSurface:
    alloc = widget.get_allocation()
    surface = cairo.ImageSurface(
        cairo.Format.ARGB32,
        alloc.width,
        alloc.height,
    )
    cr = cairo.Context(surface)
    cr.set_source_rgba(255, 255, 255, 0)
    cr.rectangle(0, 0, alloc.width, alloc.height)
    cr.fill()
    widget.draw(cr)
    return surface


class HyprlandWindowButton(Button):
    """A window inside a workspace card: a rounded live preview with an app
    icon badge. Click focuses, right-click closes, drag moves to a workspace."""

    def __init__(
        self,
        window: PopupWindow,
        title: str,
        address: str,
        app_id: str,
        size: tuple[int, int],
        transform: int = 0,
    ):
        self.transform = transform % 4
        self.size = size
        self.address = address
        self.app_id = app_id
        self.title = title
        self.window: PopupWindow = window

        # minus the 1px border on each side
        self.preview = RoundedCoverImage(
            max(1, size[0] - 2), max(1, size[1] - 2), radius=WINDOW_RADIUS
        )
        badge_size = 28 if min(size) >= 60 else 18
        icon = icon_resolver.get_icon_pixbuf(app_id, badge_size)
        super().__init__(
            name="overview-client-box",
            tooltip_text=title,
            size=size,
            child=Overlay(
                child=self.preview,
                overlays=Box(
                    name="overview-icon",
                    h_align="center",
                    v_align="end" if min(size) >= 60 else "center",
                    children=Image(pixbuf=icon),
                ),
            ),
            on_clicked=self.on_button_click,
            on_button_press_event=lambda _, event: (
                connection.send_command(
                    f"/dispatch hl.dsp.window.close({{ window = 'address:{address}' }})"
                )
                if event.button == 3
                else None
            ),
            on_drag_data_get=lambda _s, _c, data, *_: data.set_text(
                address, len(address)
            ),
            on_drag_begin=lambda _, context: Gtk.drag_set_icon_surface(
                context, createSurfaceFromWidget(self)
            ),
        )

        self.drag_source_set(
            start_button_mask=Gdk.ModifierType.BUTTON1_MASK,
            targets=TARGET,
            actions=Gdk.DragAction.COPY,
        )

    def start_preview(self, owner: object, window_size: tuple[int, int]):
        """Show a live preview of the window, as part of `owner`'s previews."""
        scale = self.get_scale_factor()
        width, height = self.size
        # windows on a rotated monitor are captured unrotated: ask for the
        # turned size and let the preview turn it back
        if self.transform % 2:
            width, height = height, width
            window_size = (window_size[1], window_size[0])
        frame_width, frame_height = cover_size(
            window_size, width * scale, height * scale
        )
        last = config.window_previews.subscribe(
            owner,
            self.address,
            frame_width,
            frame_height,
            lambda surface: self.preview.set_surface(surface, self.transform),
            fps=PREVIEW_FPS,
        )
        if last is not None:
            self.preview.set_surface(last, self.transform)

    def on_button_click(self, *_):
        # Hyprland 0.56+ (Lua config) rejects the old "focuswindow address:..." form
        connection.send_command(
            f"/dispatch hl.dsp.focus({{ window = 'address:{self.address}' }})"
        )
        self.window.toggle_popup()


class MonitorGeometry:
    """A monitor's logical layout rectangle (after scale and rotation)."""

    def __init__(self, monitor: dict):
        self.id: int = monitor["id"]
        self.name: str = monitor["name"]
        self.x: int = monitor["x"]
        self.y: int = monitor["y"]
        self.transform: int = monitor["transform"]
        width = monitor["width"] / monitor["scale"]
        height = monitor["height"] / monitor["scale"]
        # odd transforms are 90/270 degree rotations
        if self.transform % 2 == 1:
            width, height = height, width
        self.width: float = width
        self.height: float = height

    @property
    def preview_scale(self) -> float:
        return PREVIEW_HEIGHT / self.height

    @property
    def preview_size(self) -> tuple[int, int]:
        return (round(self.width * self.preview_scale), PREVIEW_HEIGHT)


class WorkspaceCard(Box):
    """
    One workspace: the wallpaper as a rounded backdrop, its windows on top, and
    a number chip. Highlighted when active on its monitor (more strongly when
    focused) and while a window is dragged over it; dropping moves the window.
    """

    def __init__(
        self,
        workspace_id: int,
        size: tuple[int, int],
        wallpaper_path: str | None,
        fixed: Gtk.Fixed | None,
        active: bool,
        focused: bool,
        monitor_name: str | None = None,
    ):
        self.wallpaper_path = wallpaper_path
        self.wallpaper_monitor: str | None = None  # monitor whose wallpaper it shows
        self.backdrop = RoundedCoverImage(size[0], size[1], radius=CARD_RADIUS)
        overlays: list[Gtk.Widget] = [
            Box(name="overview-workspace-dim", size=size),
        ]
        if fixed is not None:
            overlays.append(fixed)
        overlays.append(
            Box(
                name="overview-workspace-chip",
                h_align="start",
                v_align="start",
                children=Label(label=str(workspace_id)),
            )
        )
        if monitor_name:
            # which screen an active workspace is showing on
            overlays.append(
                Box(
                    name="overview-monitor-chip",
                    h_align="end",
                    v_align="start",
                    children=Label(label=monitor_name),
                )
            )
        self.event_box = EventBox(
            child=Overlay(child=self.backdrop, overlays=overlays),
            on_drag_data_received=lambda _w, _c, _x, _y, data, *_: (
                move_window_to_workspace(data.get_data().decode(), workspace_id)
            ),
            on_drag_motion=lambda *_: self.add_style_class("drop-target") or False,
            on_drag_leave=lambda *_: self.remove_style_class("drop-target"),
        )
        self.event_box.drag_dest_set(Gtk.DestDefaults.ALL, TARGET, Gdk.DragAction.COPY)
        super().__init__(
            name="overview-workspace",
            style_classes=(["active"] if active else [])
            + (["focused"] if focused else [])
            + ([] if fixed is not None else ["empty"]),
            children=self.event_box,
        )
        if fixed is not None:
            fixed.show_all()


class Overview(PopupWindow):
    def __init__(self):
        # self.client_output = ClientOutput()
        self.subtitle = Label(name="overview-subtitle", h_align="start")
        header = CenterBox(
            name="overview-header",
            start_children=Box(
                orientation="v",
                children=[
                    Label("Overview", name="overview-title", h_align="start"),
                    self.subtitle,
                ],
            ),
            end_children=Label(
                "Click to focus · Drag to move · Right-click to close",
                name="overview-hint",
                v_align="center",
            ),
        )
        self.grid = Box(orientation="v", spacing=16)
        self.overview_box = Box(
            name="overview-window",
            orientation="v",
            spacing=16,
            children=[header, self.grid],
        )
        self.workspace_boxes: dict[int, Gtk.Fixed] = {}
        self.clients: dict[str, HyprlandWindowButton] = {}
        self._update_timeout_id: int | None = None
        self._cards: list[WorkspaceCard] = []
        # wallpaper backdrop, loaded once per path and shared by every card
        # decoded wallpapers by path, shared by every card on that monitor
        self._wallpapers: dict[str, GdkPixbuf.Pixbuf] = {}
        self._loading_wallpapers: set[str] = set()

        connection.connect("event::openwindow", self.do_update)
        connection.connect("event::closewindow", self.do_update)
        connection.connect("event::movewindow", self.do_update)

        # self.client_output.connect("frame-ready", update_pixbuf)

        super().__init__(
            namespace="fabric-overview",
            enable_inhibitor=True,
            anchor="center",
            keyboard_mode="on-demand",
            transition_type="crossfade",
            child=self.overview_box,
        )
        # stop capturing however the overview closes (toggle, Escape, click
        # outside)
        self.reveal_child.revealer.connect(
            "notify::reveal-child",
            lambda revealer, _: (
                None
                if revealer.get_reveal_child()
                else config.window_previews.unsubscribe(self)
            ),
        )

    def update(self, signal_update=False):
        config.window_previews.unsubscribe(self)
        for client in self.clients.values():
            client.destroy()
        self.clients.clear()

        for workspace in self.workspace_boxes.values():
            workspace.destroy()
        self.workspace_boxes.clear()

        monitor_list = json.loads(connection.send_command("j/monitors").reply.decode())
        monitors = {m["id"]: MonitorGeometry(m) for m in monitor_list}
        focused_monitor = next(
            (m["id"] for m in monitor_list if m.get("focused")),
            monitor_list[0]["id"],
        )
        # the workspace shown on each monitor, and the one with focus
        active_workspaces = {
            m["activeWorkspace"]["id"]: m["name"] for m in monitor_list
        }
        focused_workspace = next(
            m["activeWorkspace"]["id"]
            for m in monitor_list
            if m["id"] == focused_monitor
        )
        # existing workspaces report their monitor; a workspace that doesn't
        # exist yet would be created on the focused monitor
        workspace_monitors: dict[int, int] = {
            ws["id"]: ws["monitorID"]
            for ws in json.loads(connection.send_command("j/workspaces").reply.decode())
            if ws["monitorID"] in monitors
        }

        client_sizes: dict[str, tuple[int, int]] = {}

        def monitor_for(workspace_id: int) -> MonitorGeometry:
            return monitors[workspace_monitors.get(workspace_id, focused_monitor)]

        for client in json.loads(
            str(connection.send_command("j/clients").reply.decode())
        ):
            workspace_id = client["workspace"]["id"]
            # We don't want any special workspaces to be included
            if workspace_id <= 0:
                continue
            monitor = monitor_for(workspace_id)
            scale = monitor.preview_scale
            box_width, box_height = monitor.preview_size

            # position relative to the monitor, clamped so a window that hangs
            # off-screen can't grow the preview beyond its box
            x = min(max(0, round((client["at"][0] - monitor.x) * scale)), box_width - 1)
            y = min(
                max(0, round((client["at"][1] - monitor.y) * scale)), box_height - 1
            )
            width = max(8, min(round(client["size"][0] * scale), box_width - x))
            height = max(8, min(round(client["size"][1] * scale), box_height - y))

            client_sizes[client["address"]] = tuple(client["size"])
            self.clients[client["address"]] = HyprlandWindowButton(
                window=self,
                title=client["title"],
                address=client["address"],
                app_id=client["initialClass"],
                size=(width, height),
                transform=monitor.transform,
            )
            if workspace_id not in self.workspace_boxes:
                self.workspace_boxes[workspace_id] = Gtk.Fixed.new()
            self.workspace_boxes[workspace_id].put(
                self.clients[client["address"]], x, y
            )
        self._cards = [
            WorkspaceCard(
                w_id,
                monitor_for(w_id).preview_size,
                wallpaper_for_monitor(monitor_for(w_id).name),
                self.workspace_boxes.get(w_id),
                active=w_id in active_workspaces,
                focused=w_id == focused_workspace,
                # only worth labelling when there is more than one screen
                monitor_name=active_workspaces.get(w_id) if len(monitors) > 1 else None,
            )
            for w_id in WORKSPACES
        ]
        rows = [
            Box(spacing=16, children=self._cards[i : i + COLUMNS])
            for i in range(0, len(self._cards), COLUMNS)
        ]
        self.grid.children = rows

        windows = len(self.clients)
        in_use = len(self.workspace_boxes)
        self.subtitle.set_label(
            f"{windows} window{'s' if windows != 1 else ''} · "
            f"{in_use} workspace{'s' if in_use != 1 else ''} in use · "
            f"{len(monitors)} monitor{'s' if len(monitors) != 1 else ''}"
        )
        for card, w_id in zip(self._cards, WORKSPACES):
            card.wallpaper_monitor = monitor_for(w_id).name
        self._sync_wallpapers()

        for client_addr, button in self.clients.items():
            button.start_preview(self, client_sizes[client_addr])

    def _sync_wallpapers(self):
        """
        Show the saved wallpaper right away, then correct it with what
        hyprpaper reports each monitor is actually showing (it may have been
        changed outside the picker).
        """
        self._apply_wallpaper()
        cards = self._cards

        def on_active(active: dict[str, str]):
            if cards is not self._cards:
                return  # the overview was rebuilt meanwhile
            changed = False
            for card in cards:
                path = active.get(card.wallpaper_monitor or "")
                if path and path != card.wallpaper_path:
                    card.wallpaper_path = path
                    changed = True
            if changed:
                self._apply_wallpaper()

        query_active_wallpapers(on_active)

    def _apply_wallpaper(self):
        """Give each card its monitor's wallpaper, loading any not yet decoded."""
        for card in self._cards:
            path = card.wallpaper_path
            if path is None:
                continue
            if path in self._wallpapers:
                card.backdrop.set_pixbuf(self._wallpapers[path])
            elif path not in self._loading_wallpapers:
                self._load_wallpaper(path)
        # drop decoded wallpapers no card uses any more
        in_use = {card.wallpaper_path for card in self._cards}
        for path in [p for p in self._wallpapers if p not in in_use]:
            del self._wallpapers[path]

    def _load_wallpaper(self, path: str):
        self._loading_wallpapers.add(path)

        def on_pixbuf(_src, result: Gio.AsyncResult):
            self._loading_wallpapers.discard(path)
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_stream_finish(result)
            except GLib.Error as e:
                logger.error(f"[Overview] Couldn't load wallpaper {path}: {e.message}")
                return
            self._wallpapers[path] = pixbuf
            for card in self._cards:
                if card.wallpaper_path == path:
                    card.backdrop.set_pixbuf(pixbuf)

        def on_read(file: Gio.File, result: Gio.AsyncResult):
            try:
                stream = file.read_finish(result)
            except GLib.Error as e:
                self._loading_wallpapers.discard(path)
                logger.error(f"[Overview] Couldn't open wallpaper {path}: {e.message}")
                return
            # big enough for sharp HiDPI cards, small enough to stay cheap
            GdkPixbuf.Pixbuf.new_from_stream_at_scale_async(
                stream, 1024, -1, True, None, on_pixbuf
            )

        Gio.File.new_for_path(path).read_async(GLib.PRIORITY_DEFAULT, None, on_read)

    def do_update(self, *_):
        # Window events often arrive in bursts (e.g. moving a window emits
        # several), and update() recaptures every window synchronously, so
        # coalesce them into a single update.
        if not self.popup_visible or self._update_timeout_id is not None:
            return
        logger.info(f"[Overview] Updating for :{_[1].name}")
        self._update_timeout_id = GLib.timeout_add(100, self._do_scheduled_update)

    def _do_scheduled_update(self):
        self._update_timeout_id = None
        if self.popup_visible:
            self.update(signal_update=True)
        return False

    def toggle_popup(self, monitor: bool | None = None):
        self.update() if not self.popup_visible else None
        return super().toggle_popup(monitor=False)
