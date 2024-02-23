import fabric
from loguru import logger
from fabric.widgets.box import Box
from fabric.widgets.wayland import Window
from fabric.widgets.centerbox import CenterBox
from widgets.kinetic_scroller import KineticScroll
from fabric.widgets.scale import Scale
from fabric.utils import (
    set_stylesheet_from_file,
    get_relative_path,
)
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
                              max_value=1000,
                              orientation="h",
                              draw_value=False,
                              name="seek-bar")
        self.scroller.set_size_request(800, -1)
        self.scrollBox = Box(name="box",
                             children=self.scroller,
                             style= "padding: 50px"
                             )
        # self.workspacescroll = EventBox(style="background-color: black;",events="smooth-scroll", )

        self.workspacescroll = KineticScroll(
            style = "background-color: rgba(0,0,0,0.25);",
            multiplier=10,
            min_value=0,
            max_value=1000,
            children=CenterBox(orientation="v",center_widgets=[self.scrollBox,Box(size=100)])
        )
        self.scroller.connect("scroll-event", self.on_scroll)
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