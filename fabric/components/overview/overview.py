import json

import cairo
import gi
from utils.icon_resolver import IconResolver
from widgets.popup_window_v2 import PopupWindow

from fabric.hyprland.service import Hyprland
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk

icon_resolver = IconResolver()
connection = Hyprland()
SCALE = 0.15


# Credit to Aylur for the drag and drop code
TARGET = [Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)]


# Credit to Aylur for the createSurfaceFromWidget code
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
        title: str,
        address: str,
        app_id: str,
        size,
    ):
        self.address = address
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

    def on_button_click(self, *_):
        connection.send_command(f"/dispatch focuswindow address:{self.address}")
        self.window.toggle_popup()


class WorkspaceEventBox(EventBox):
    def __init__(self, workspace_id: int, fixed: Gtk.Fixed | None = None):
        self.fixed = fixed
        super().__init__(
            name="overview-workspace-bg",
            child=fixed
            if fixed
            # TODO this is lazy, do it right later lol
            else Image(
                pixbuf=Gtk.IconTheme()
                .get_default()
                .load_icon("list-add", 36, Gtk.IconLookupFlags.FORCE_SIZE)
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
        if fixed:
            fixed.put(
                # FIXME: Don't hardcode this value, it should be dynamic to the monitor, use HyprctlWithMonitors
                Box(size=(int(1920 * SCALE), int(1080 * SCALE))),
                0,
                0,
            )
            fixed.show_all()


class Overview(PopupWindow):
    def __init__(self):
        self.overview_box = Box(name="overview-window")
        self.workspace_boxes: dict[int, Box] = {}
        self.clients: dict[str, HyprlandWindowButton] = {}
        self.update()

        connection.connect("event::openwindow", self.do_update)
        connection.connect("event::closewindow", self.do_update)
        connection.connect("event::movewindow", self.do_update)

        super().__init__(
            anchor="center",
            keyboard_mode="on-demand",
            transition_type="crossfade",
            child=self.overview_box,
        )

    def update(self):
        for client in self.clients.values():
            client.destroy()
        self.clients.clear()

        for workspace in self.workspace_boxes.values():
            workspace.destroy()
        self.workspace_boxes.clear()

        self.overview_box.children = []

        monitors = {
            monitor["id"]: (monitor["x"], monitor["y"])
            for monitor in json.loads(
                connection.send_command("j/monitors").reply.decode()
            )
        }

        for client in json.loads(
            str(connection.send_command("j/clients").reply.decode())
        ):
            # We don't want any special workspaces to be included
            if client["workspace"]["id"] > 0:
                self.clients[client["address"]] = HyprlandWindowButton(
                    window=self,
                    title=client["title"],
                    address=client["address"],
                    app_id=client["initialClass"],
                    size=(client["size"][0] * SCALE, client["size"][1] * SCALE),
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
        total_workspaces = (
            range(1, max(self.workspace_boxes.keys()) + 2)
            if len(self.workspace_boxes) != 0
            else []
        )
        for w_id in total_workspaces:
            self.overview_box.add(
                Box(
                    name="overview-workspace-box",
                    orientation="vertical",
                    h_align="end",
                    v_align="end",
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

    def do_update(self, *_):
        print("Updating for :", _[1].name)
        self.update()

    def toggle_popup(self, monitor: bool | None = None):
        self.update()
        return super().toggle_popup(monitor=False)
