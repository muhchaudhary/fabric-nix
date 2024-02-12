import json
import fabric
import os
from loguru import logger
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.wayland import Window
from fabric.widgets.overlay import Overlay
from fabric.widgets.eventbox import EventBox
from fabric.widgets.centerbox import CenterBox
from fabric.hyprland.service import Connection
from fabric.utils import (
    set_stylesheet_from_file,
    bulk_replace,
    monitor_file,
    invoke_repeater,
    get_relative_path,
)
connection = Connection()
MAX_OPEN_WRKSPACE = 7

def get_open_windows() -> dict:
    clients = json.loads(
        str(
            connection.send_command(
                "j/clients",
            ).reply.decode()
        )
    )
    cdict = {}
    for client in clients:
        if client["workspace"]["id"] not in cdict:
            cdict[client["workspace"]["id"]] = [(client["class"], client["at"])]
        else:
            cdict[client["workspace"]["id"]].append((client["class"], client["at"]))
    return cdict

class Overview(Window):
    def __init__(
        self,
    ):
        super().__init__(
            layer="overlay",
            anchor="left center right",
            margin="10px 10px -2px 10px",
            exclusive=True,
            visible=True,
        )
        self.center_box = CenterBox(
            name="main-window",
            spacing=10,
            center_widgets=self.make_windows_children(getOpenWindows()),
            )
        self.add(self.center_box)
        self.show_all()

    def make_windows_children(self, cdict):
        boxes = []
        for w in sorted(cdict.keys())[1:]:
            labels = []
            for clients in cdict[w]:
                labels.append(Label(clients[0]))
            windows_box = Box(
                name="window-box",
                spacing=10,
                children=labels,
            )
            boxes.append(windows_box)
        return boxes

def apply_style(*args):
    logger.info("[Bar] CSS applied")
    return set_stylesheet_from_file(get_relative_path("overview.css"))

if __name__ == "__main__":
    bar = Overview()
    clients = getOpenWindows()
    apply_style()
    fabric.start()