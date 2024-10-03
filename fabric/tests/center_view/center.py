import math
import os

from fabric.audio import Audio
from fabric.core import Application
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.shapes import Corner
from fabric.widgets.wayland import WaylandWindow as Window


class CenterView(Revealer):
    def __init__(self):
        self.background_color = "black"
        self.raidus = 20

        self.left_corner = Box(
            children=Corner(
                orientation="top-right",
                style=f"background-color: {self.background_color};",
                size=self.raidus,
            ),
            style=f"margin-bottom: {self.raidus * math.pi}px;",
        )

        self.right_corner = Box(
            children=Corner(
                orientation="top-left",
                style=f"background-color: {self.background_color};",
                size=self.raidus,
            ),
            style=f"margin-bottom: {self.raidus * math.pi}px;",
        )

        self.item_revealer = Revealer(
            child=CenterBox(
                style="padding-left: 50px; padding-right: 50px",
                center_children=[Label("Hello Fabric", justification="center")],
                orientation="horizontal",
            ),
            transition_type="crossfade",
            transition_duration=400,
            child_revealed=True,
        )

        self.centerview_window = Box(
            style=(
                f"background-color: {self.background_color};"
                + f"border-bottom-right-radius: {self.raidus}px;  "
                + f"border-bottom-left-radius: {self.raidus}px;"
            ),
            children=self.item_revealer,
        )

        super().__init__(
            child=Box(
                children=[self.left_corner, self.centerview_window, self.right_corner],
            ),
            transition_type="slide-down",
            transition_duration=400,
            child_revealed=True,
        )

        self.connect("notify::child-revealed", self.on_child_reveal)

    def on_child_reveal(self, *_):
        if self.fully_revealed:
            self.item_revealer.reveal()
        elif not self.child_revealed:
            self.item_revealer.unreveal()


# TODO: Create a more generic centerview popup class
# TODO: This is just for testing
class CenterViewOSD(Revealer):
    def __init__(self):
        # Parametrize later
        self.background_color = "black"
        # Should be set with css later
        self.raidus = 20
        self.audio = Audio()

        # System OSD stuff
        # ------------------------------------------------------------------------
        self.accent = "red"
        self.vol = 0

        self.overlay_fill_box = Box(style="min-width: 300px; min-height: 40px;")
        self.icon = Image()

        # ------------------------------------------------------------------------

        self.left_corner = Box(
            children=Corner(
                orientation="top-right",
                style=f"background-color: {self.background_color};",
                size=self.raidus,
            ),
            style=f"margin-bottom: {self.raidus * math.pi}px;",
        )

        self.right_corner = Box(
            children=Corner(
                orientation="top-left",
                style=f"background-color: {self.background_color};",
                size=self.raidus,
            ),
            style=f"margin-bottom: {self.raidus * math.pi}px;",
        )

        self.item_revealer = Revealer(
            child=CenterBox(
                style="padding-left: 50px; padding-right: 50px",
                center_children=[Label("Hello Fabric", justification="center")],
                end_children=[self.icon, self.overlay_fill_box],
                orientation="vertical",
            ),
            transition_type="crossfade",
            transition_duration=400,
            child_revealed=True,
        )

        self.centerview_window = Box(
            style=(
                f"background-color: {self.background_color};"
                + f"border-bottom-right-radius: {self.raidus}px;  "
                + f"border-bottom-left-radius: {self.raidus}px;"
            ),
            children=self.item_revealer,
        )

        super().__init__(
            child=Box(
                children=[self.left_corner, self.centerview_window, self.right_corner],
            ),
            transition_type="slide-down",
            transition_duration=400,
            child_revealed=True,
        )

        self.connect("notify::child-revealed", self.on_child_reveal)

    def on_child_reveal(self, *_):
        if self.fully_revealed:
            self.item_revealer.reveal()
        elif not self.child_revealed:
            self.item_revealer.unreveal()

    def update_label_audio(self, *args):
        icon_name = "-".join(str(self.audio.speaker.icon_name).split("-")[0:2])
        self.icon.set_from_icon_name(icon_name + "-symbolic", 6)
        self.vol = self.audio.speaker.volume
        quick_accent = self.accent
        if self.audio.speaker.muted:
            quick_accent = "#a89984"
        self.overlay_fill_box.set_style(
            f"background-image: linear-gradient(to right, alpha({quick_accent}, 0.8) {round(self.vol)}%, alpha(#303030, 0.8) {round(self.vol)}%); min-width: 500px; min-height: 40px;",
        )

    def enable_popup(self, type: str):
        if type == "sound":
            self.update_label_audio()
        elif type == "brightness":
            self.update_label_brightness()
        elif type == "kbd":
            self.update_label_keyboard()

if __name__ == "__main__":
    view = CenterView()
    window = Window(
        layer="top",
        child=Box(children=view, style="padding-bottom: 1px;"),
        anchor="top",
    )
    app = Application("centerview")
    app.set_stylesheet_from_string(
        """
        * {
        all: unset;
        font-family: "roboto slab";
        font-weight: 900;
        font-size: 45px;
        }
        """
    )
    app.run()
