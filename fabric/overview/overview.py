import json
import fabric
import os
from loguru import logger
from fabric.widgets.box import Box
from fabric.widgets.wayland import Window
from fabric.widgets.eventbox import EventBox
from fabric.widgets.centerbox import CenterBox
from kinetic_scroller import KineticScroll
from fabric.widgets.scale import Scale
from fabric.utils import (
    set_stylesheet_from_file,
    get_relative_path,
    invoke_repeater,
    clamp,
)
from gi.repository import Gdk

class Overview(Window):
    def __init__(
        self,
    ):
        super().__init__(
            layer="overlay",
            anchor="center",
            exclusive=True,
            visible=True,
        )
        self.scroll_value = 0
        self.iters = 0

        self.scroller = Scale(min_value=0,
                              max_value=100,
                              orientation="h",
                              draw_value=False,
                              name="seek-bar")
        self.scroller.set_size_request(500, -1)
        self.scrollBox = Box(name="box",
                             children=self.scroller,
                             )
        # self.workspacescroll = EventBox(style="background-color: black;",events="smooth-scroll", )
        self.workspacescroll = KineticScroll(
            mult=2,
            min_value=0,
            max_value=100,
            children=CenterBox(orientation="v",center_widgets=Box(size=100, style="background-color: red;") ,left_widgets=self.scrollBox)
        )
        self.workspacescroll.connect("smooth-scroll-event", self.on_scroll)

        self.add(self.workspacescroll)
        self.show_all()

    def on_scroll(self,widget, value):
        self.scroller.set_value(value)

def apply_style(*args):
    logger.info("[Bar] CSS applied")
    return set_stylesheet_from_file(get_relative_path("../bar/bar.css"))

if __name__ == "__main__":
    bar = Overview()
    apply_style()
    fabric.start()