import json
import gi

from fabric.core import Application
from fabric.widgets.eventbox import EventBox
from fabric.hyprland.service import Hyprland
from fabric.utils import get_relative_path, monitor_file
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from widgets.popup_window_v2 import PopupWindow
from fabric.widgets.label import Label
from utils.icon_resolver import IconResolver
from fabric.widgets.image import Image

import cairo

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk

icon_resolver = IconResolver()
connection = Hyprland()
SCALE = 0.18


# Credit to Aylur for the drag and drop code
TARGET = [Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)]


def createSurfaceFromWidget(widget: Gtk.Widget):
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
        address: str,
        app_id: str,
        workspace_id: int,
        size,
        at,
    ):
        self.address = address
        self.size = size
        self.at = at
        self.workspace_id = workspace_id
        self.window: PopupWindow = window
        super().__init__(
            name="overview-client-box",
            image=Image(pixbuf=icon_resolver.get_icon_pixbuf(app_id, 36)),
            on_clicked=self.on_button_click,
            on_button_press_event=lambda _, event: connection.send_command(
                f"/dispatch closewindow address:{address}"
            )
            if event.button == 3
            else None,
            size=size,
        )

        self.drag_source_set(
            start_button_mask=Gdk.ModifierType.BUTTON1_MASK,
            targets=TARGET,
            actions=Gdk.DragAction.COPY,
        )
        self.connect(
            "drag-data-get",
            lambda _s, _c, data, *_: data.set_text(address, len(address)),
        )
        self.connect(
            "drag-begin",
            lambda _, context: [
                Gtk.drag_set_icon_surface(context, createSurfaceFromWidget(self)),
            ],
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
            child=fixed
            if fixed
            else Image(pixbuf=IconResolver().get_icon_pixbuf("list-add", 36)),
            name="overview-workspace-bg",
        )
        self.drag_dest_set(
            Gtk.DestDefaults.ALL,
            TARGET,
            Gdk.DragAction.COPY,
        )
        self.connect(
            "drag-data-received",
            lambda _w, _c, _x, _y, data, *_: connection.send_command(
                f"/dispatch movetoworkspacesilent {workspace_id},address:{data.get_data().decode()}"
            ),
        )


class Overview(PopupWindow):
    def __init__(self):
        self.overview_box = Box(name="overview-window")
        self.workspace_boxes: dict[int, Box] = {}
        self.clients: dict[str, HyprlandWindowButton] = {}
        self.update()

        connection.connect("event::openwindow", self.do_update)
        connection.connect("event::closewindow", self.do_update)
        connection.connect("event::movewindowv2", self.do_update)
        # connection.connect("event::createworkspace", self.do_update)

        super().__init__(
            anchor="center",
            keyboard_mode="on-demand",
            transition_type="crossfade",
            child=Box(style="padding: 10px;", children=self.overview_box),
        )

    def update(self):
        for client in self.clients.values():
            client.destroy()
        self.clients = {}

        for workspace in self.workspace_boxes.values():
            workspace.destroy()
        self.workspace_boxes = {}

        self.overview_box.children = []

        for client in json.loads(
            str(connection.send_command("j/clients").reply.decode())
        ):
            print(client)
            # We don't want any special workspaces to be included
            if client["workspace"]["id"] > 0:
                self.clients[client["address"]] = HyprlandWindowButton(
                    window=self,
                    address=client["address"],
                    app_id=client["initialClass"],
                    workspace_id=client["workspace"]["id"],
                    at=client["at"],
                    size=(client["size"][0] * SCALE, client["size"][1] * SCALE),
                )
                if client["workspace"]["id"] not in self.workspace_boxes:
                    self.workspace_boxes.update(
                        {client["workspace"]["id"]: Gtk.Fixed.new()}
                    )
                self.workspace_boxes[client["workspace"]["id"]].put(
                    self.clients[client["address"]],
                    client["at"][0] * SCALE,
                    client["at"][1] * SCALE,
                )
        # TODO: add (+) button to create workspace in between if there is space empty:
        #   EX: W1 , (+) , W7 will place a workspace in W2 or W6 (prefer lower number)
        total_workspaces = (
            range(1, max(self.workspace_boxes.keys()) + 1)
            if len(self.workspace_boxes) != 0
            else []
        )
        for w_id in total_workspaces:
            if w_id in self.workspace_boxes:
                self.workspace_boxes[w_id].put(
                    # FIXME: Don't hardcode this value, it should be dynamic to the monitor, use HyprctlWithMonitors
                    Box(size=(int(1920 * SCALE), int(1080 * SCALE))),
                    0,
                    0,
                )
                self.overview_box.add(
                    Box(
                        name="overview-workspace-box",
                        orientation="vertical",
                        children=[
                            WorkspaceEventBox(w_id, self.workspace_boxes[w_id]),
                            Label(f"Workspace {w_id}"),
                        ],
                    )
                )
                self.workspace_boxes[w_id].show_all()

            else:
                self.overview_box.add(
                    Box(
                        orientation="vertical",
                        name="overview-workspace-box",
                        children=[WorkspaceEventBox(w_id), Label(f"Workspace {w_id}")],
                    )
                )

    def do_update(self, *_):
        print("Updating for :", _[1].name)
        self.update()
