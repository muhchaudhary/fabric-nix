import json

import gi

import fabric
from fabric.hyprland.service import Connection
from fabric.utils import get_relative_path, set_stylesheet_from_file
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.eventbox import EventBox
from fabric.widgets.scale import Scale
from fabric.widgets.wayland import WaylandWindow

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

connection = Connection()
SCALE = 0.16


class HyprlandWindow(Button):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class WorkspaceBox(Box):
    def __init__(self, workspace_id: str, **kwargs):
        self.workspace_id = workspace_id
        super().__init__(**kwargs)

    def on_window_open(self, *args):
        pass

    def on_window_close(self, *args):
        pass


class Overview(WaylandWindow):
    def __init__(self):
        self.overview_box = Box(style="padding: 1px;")
        self.workspace_boxes: dict[int, Gtk.Fixed] = {}

        self.clients: dict[str, WorkspaceBox] = {}

        curr_clients: list = json.loads(
            str(connection.send_command("j/clients").reply.decode())
        )

        super().__init__(
            layer="overlay",
            anchor="center",
            exclusive=True,
            visible=True,
            children=self.overview_box,
        )
        self.show_all()

        for client in curr_clients:
            self.create_client_box(client)
        connection.connect("openwindow", self.on_window_open)
        connection.connect("closewindow", self.on_window_close)

    def reset_fixed_box(self):
        workspace_ids = self.workspace_boxes.keys()
        for id in workspace_ids:
            for child in self.workspace_boxes[id].get_children():
                self.workspace_boxes[id].remove(child)
                child.destroy()

    def create_client_box(self, client: dict):
        addr = client["address"]
        print(f"creating new box of address {addr}")
        window_box = WorkspaceBox(
            name="window-box", workspace_id=client["workspace"]["id"]
        )
        window_box.set_size_request(
            client["size"][0] * SCALE, client["size"][1] * SCALE
        )
        self.clients[addr] = window_box
        self.add_to_workspace_box(
            client["workspace"]["id"], self.clients[addr], client["at"]
        )

    def update_entire_fixed(self):
        curr_clients: list = json.loads(
            str(connection.send_command("j/clients").reply.decode())
        )

    def update_clients(self, client: dict):
        addr = client["address"]
        # print(f"updating client with address {addr}")
        if addr in self.clients:
            # print("client already existed, updating in place")
            self.clients[addr].set_size_request(
                client["size"][0] * SCALE, client["size"][1] * SCALE
            )
            self.workspace_boxes[client["workspace"]["id"]].move(
                self.clients[addr], client["at"][0] * SCALE, client["at"][1] * SCALE
            )
            return
        print("client did not exist, lets make a new one")
        window_box = Box(name="window-box")
        window_box.set_size_request(
            client["size"][0] * SCALE, client["size"][1] * SCALE
        )
        self.clients[addr] = window_box
        self.add_to_workspace_box(
            client["workspace"]["id"], self.clients[addr], client["at"]
        )

    def add_to_workspace_box(self, workspace_id: int, window_box: Box, at_pos):
        if workspace_id not in self.workspace_boxes:
            self.workspace_boxes[workspace_id] = Gtk.Fixed.new()
            self.overview_box.add(
                Box(name="workspace-box", children=self.workspace_boxes[workspace_id])
            )
            self.workspace_boxes[workspace_id].show_all()
        self.workspace_boxes[workspace_id].put(
            window_box, at_pos[0] * SCALE, at_pos[1] * SCALE
        )

    def on_window_open(self, _connection, reply):
        print(f"new window open of address 0x{reply.data[0]}")
        curr_clients: list = json.loads(
            str(connection.send_command("j/clients").reply.decode())
        )
        for client in curr_clients:
            self.update_clients(client)

    def on_window_close(self, _connection, reply):
        print(f"window closed of address 0x{reply.data[0]}")
        curr_clients: list = json.loads(
            str(connection.send_command("j/clients").reply.decode())
        )
        deleted_client = self.clients[f"0x{reply.data[0]}"]
        deleted_client.destroy()
        del self.clients[f"0x{reply.data[0]}"]
        # self.workspace_boxes[self.delete_client.workspace_id]

        for client in curr_clients:
            self.update_clients(client)


def apply_style(*args):
    return set_stylesheet_from_file(get_relative_path("overview.css"))


if __name__ == "__main__":
    bar = Overview()
    # x = WorkspaceBox()
    apply_style()
    fabric.start()
