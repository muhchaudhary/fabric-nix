from ast import Tuple
from cProfile import label
import json

import cairo
from fabric.utils import invoke_repeater
import gi
from fabric.hyprland.service import Hyprland
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from loguru import logger

from fabric_config.utils.icon_resolver import IconResolver
from fabric.widgets.eventbox import EventBox
from fabric_config.utils.pywayland_export_toplevel import ClientOutput
from fabric_config.widgets.popup_window_v2 import PopupWindow
from fabric_config.widgets.rounded_image import CustomImage

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Glace, Gtk

icon_resolver = IconResolver()
connection = Hyprland()
SCALE = 0.2

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
            on_button_press_event=lambda _, event: connection.send_command(
                f"/dispatch closewindow address:{address}"
            )
            if event.button == 3
            else None,
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
        connection.send_command(f"/dispatch focuswindow address:{self.address}")
        self.window.toggle_popup()


class WorkspaceEventBox(EventBox):
    def __init__(self, workspace_id: int, fixed: Gtk.Fixed | None = None):
        self.fixed = fixed
        super().__init__(
            h_expand=True,
            v_expand=True,
            size=(int(1920 * SCALE), int(1080 * SCALE)),
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
            on_drag_data_received=lambda _w,
            _c,
            _x,
            _y,
            data,
            *_: connection.send_command(
                f"/dispatch movetoworkspacesilent {workspace_id},address:{data.get_data().decode()}"
            ),
        )
        self.drag_dest_set(
            Gtk.DestDefaults.ALL,
            TARGET,
            Gdk.DragAction.COPY,
        )
        fixed.show_all() if fixed else None


# TODO update with monitors for later....
class Overview(PopupWindow):
    def __init__(self):
        self.glace_manager = Glace.Manager()
        # self.client_output = ClientOutput()
        self.overview_box = Box(name="overview-window", style_classes=["cool-border"], orientation="v", spacing=5)
        self.workspace_boxes: dict[int, Box] = {}
        self.clients: dict[str, HyprlandWindowButton] = {}

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

        monitors = {
            monitor["id"]: (monitor["x"], monitor["y"], monitor["transform"])
            for monitor in json.loads(
                connection.send_command("j/monitors").reply.decode()
            )
        }

        for client in json.loads(
            str(connection.send_command("j/clients").reply.decode())
        ):
            # We don't want any special workspaces to be included
            if client["workspace"]["id"] > 0:
                print(client["size"])
                self.clients[client["address"]] = HyprlandWindowButton(
                    window=self,
                    title=client["title"],
                    address=client["address"],
                    app_id=client["initialClass"],
                    size=(client["size"][0] * SCALE, client["size"][1] * SCALE),
                    transform=monitors[client["monitor"]][2],
                )
                if client["workspace"]["id"] not in self.workspace_boxes:
                    self.workspace_boxes.update(
                        {client["workspace"]["id"]: Gtk.Fixed.new()}
                    )
                self.workspace_boxes[client["workspace"]["id"]].put(
                    self.clients[client["address"]],
                    abs(client["at"][0] - monitors[client["monitor"]][0]) * SCALE,
                    abs(client["at"][1] - monitors[client["monitor"]][1]) * SCALE,
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
                            self.workspace_boxes[w_id]
                            if w_id in self.workspace_boxes
                            else None,
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
                        self.clients[address].size[0] - 7,
                        self.clients[address].size[1] - 7,
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
            invoke_repeater(
                300,
                self.glace_manager.capture_client_handle,
                int(client_addr, 16),
                False,
                update_pixbuf,
                client_addr,
                initial_call=False if signal_update else True,
            )

    def do_update(self, *_):
        if self.popup_visible:
            logger.info(f"[Overview] Updating for :{_[1].name}")
            self.update(signal_update=True)

    def toggle_popup(self, monitor: bool | None = None):
        self.update() if not self.popup_visible else None
        return super().toggle_popup(monitor=False)
