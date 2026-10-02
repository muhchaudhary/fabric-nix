import json

import cairo
import gi
from fabric.hyprland.service import Hyprland
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from hyprland_toplevel_streamer import HyprlandFrameCapture
from loguru import logger

from fabric_config.utils.icon_resolver import get_icon_resolver
from fabric_config.widgets.popup_window_v2 import PopupWindow
from fabric_config.widgets.rounded_image import CustomImage

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

icon_resolver = get_icon_resolver()
connection = Hyprland()
# Every workspace preview is this tall; its width follows the aspect ratio of
# the monitor the workspace is on, and its windows are scaled to match. This
# keeps previews consistent when monitors differ in size, scale or rotation.
PREVIEW_HEIGHT = 216


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
    def __init__(
        self,
        window: PopupWindow,
        title: str,
        address: str,
        app_id: str,
        size,
        transform: int = 0,
    ):
        self.transform = transform % 4
        self.size = size if transform in [0, 2] else (size[1], size[0])
        self.address = address
        self.app_id = app_id
        self.title = title
        self.window: PopupWindow = window
        super().__init__(
            name="overview-client-box",
            image=Image(pixbuf=icon_resolver.get_icon_pixbuf(app_id, 36)),
            tooltip_text=title,
            size=size,
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

    def update_image(self, image):
        self.set_image(
            Overlay(
                child=image,
                overlays=Image(
                    name="overview-icon",
                    pixbuf=icon_resolver.get_icon_pixbuf(self.app_id, 36),
                    h_align="center",
                    v_align="end",
                    tooltip_text=self.title,
                ),
            )
        )

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


class WorkspaceEventBox(EventBox):
    def __init__(
        self,
        workspace_id: int,
        size: tuple[int, int],
        fixed: Gtk.Fixed | None = None,
    ):
        self.fixed = fixed
        super().__init__(
            h_expand=False,
            v_expand=False,
            size=size,
            name="overview-workspace-bg",
            style_classes=["cool-border"],
            child=fixed
            if fixed
            # TODO this is lazy, do it right later lol
            else Image(
                h_expand=True,
                v_expand=True,
                pixbuf=Gtk.IconTheme()
                .get_default()
                .load_icon("list-add", 64, Gtk.IconLookupFlags.FORCE_SIZE),
            ),
            on_drag_data_received=lambda _w, _c, _x, _y, data, *_: (
                move_window_to_workspace(data.get_data().decode(), workspace_id)
            ),
        )
        self.drag_dest_set(
            Gtk.DestDefaults.ALL,
            TARGET,
            Gdk.DragAction.COPY,
        )
        fixed.show_all() if fixed else None


class Overview(PopupWindow):
    def __init__(self):
        self._capture = HyprlandFrameCapture()
        # self.client_output = ClientOutput()
        self.overview_box = Box(
            name="overview-window",
            style_classes=["cool-border"],
            orientation="v",
            spacing=5,
        )
        self.workspace_boxes: dict[int, Box] = {}
        self.clients: dict[str, HyprlandWindowButton] = {}
        self._update_timeout_id: int | None = None

        connection.connect("event::openwindow", self.do_update)
        connection.connect("event::closewindow", self.do_update)
        connection.connect("event::movewindow", self.do_update)

        # self.client_output.connect("frame-ready", update_pixbuf)

        super().__init__(
            enable_inhibitor=True,
            anchor="center",
            keyboard_mode="on-demand",
            transition_type="crossfade",
            child=self.overview_box,
        )

    def update(self, signal_update=False):
        for client in self.clients.values():
            client.destroy()
        self.clients.clear()

        for workspace in self.workspace_boxes.values():
            workspace.destroy()
        self.workspace_boxes.clear()

        self.overview_box_rows = [Box(), Box()]
        self.overview_box.children = self.overview_box_rows

        monitor_list = json.loads(connection.send_command("j/monitors").reply.decode())
        monitors = {m["id"]: MonitorGeometry(m) for m in monitor_list}
        focused_monitor = next(
            (m["id"] for m in monitor_list if m.get("focused")),
            monitor_list[0]["id"],
        )
        # existing workspaces report their monitor; a workspace that doesn't
        # exist yet would be created on the focused monitor
        workspace_monitors: dict[int, int] = {
            ws["id"]: ws["monitorID"]
            for ws in json.loads(connection.send_command("j/workspaces").reply.decode())
            if ws["monitorID"] in monitors
        }

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
        # total_workspaces = (
        #     range(1, max(self.workspace_boxes.keys()) + 2)
        #     if len(self.workspace_boxes) != 0
        #     else []
        # )
        for w_id in range(1, 9):
            if w_id <= 4:
                overview_row = self.overview_box.children[0]
            else:
                overview_row = self.overview_box.children[1]
            overview_row.add(
                Box(
                    name="overview-workspace-box",
                    orientation="vertical",
                    children=[
                        WorkspaceEventBox(
                            w_id,
                            monitor_for(w_id).preview_size,
                            self.workspace_boxes.get(w_id),
                        ),
                        Label(f"Workspace {w_id}"),
                    ],
                )
            )

        def update_pixbuf(pixbuf, address):
            if address not in self.clients:
                return
            self.clients[address].update_image(
                CustomImage(
                    name="overview-frame",
                    pixbuf=GdkPixbuf.Pixbuf.scale_simple(
                        pixbuf,
                        max(1, self.clients[address].size[0] - 7),
                        max(1, self.clients[address].size[1] - 7),
                        GdkPixbuf.InterpType.BILINEAR,
                    ).rotate_simple(
                        {
                            0: GdkPixbuf.PixbufRotation.NONE,
                            1: GdkPixbuf.PixbufRotation.CLOCKWISE,
                            2: GdkPixbuf.PixbufRotation.UPSIDEDOWN,
                            3: GdkPixbuf.PixbufRotation.COUNTERCLOCKWISE,
                        }.get(
                            self.clients[address].transform,
                            GdkPixbuf.PixbufRotation.NONE,
                        )
                    ),
                )
            )

        for client_addr in self.clients.keys():
            try:
                frame = self._capture.capture(
                    int(client_addr, 16), overlay_cursor=False, rgba=True
                )
                update_pixbuf(
                    GdkPixbuf.Pixbuf.new_from_bytes(
                        GLib.Bytes.new(frame.data),
                        GdkPixbuf.Colorspace.RGB,
                        True,  # has_alpha
                        8,  # bits per sample
                        frame.width,
                        frame.height,
                        frame.rowstride,
                    ),
                    client_addr,
                )
            except Exception as e:
                logger.error(f"Error capturing client {client_addr}: {e}")

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
