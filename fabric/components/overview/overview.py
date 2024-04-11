import fabric
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.eventbox import EventBox
from fabric.widgets.scale import Scale
from fabric.widgets.wayland import Window
from kinetic_scroller import KineticScroll


class Overview(Window):
    def __init__(self):
        super().__init__(
            layer="overlay",
            anchor="center",
            exclusive=True,
            visible=True,
        )
        self.scroll_value = 0
        self.multiple = 1
        self.iters = 0

        self.scroller = Scale(
            min_value=0,
            max_value=1000,
            orientation="h",
            draw_value=False,
            name="seek-bar",
        )
        self.scroller.set_size_request(800, -1)
        self.scrollBox = Box(name="box", children=self.scroller, style="padding: 50px")
        self.workspacescroll2 = EventBox(
            style="background-color: black;",
            events="smooth-scroll",
        )
        self.workspacescroll2.set_size_request(500, 100)

        self.workspacescroll = KineticScroll(
            style="background-color: rgba(0,0,0,0.25);",
            multiplier=10,
            min_value=0,
            max_value=1000,
            children=CenterBox(
                orientation="v", center_widgets=[self.scrollBox, Box(size=100)]
            ),
        )
        self.scroller.connect("scroll-event", self.on_scroll)
        self.workspacescroll.connect("smooth-scroll-event", self.on_scroll)
        self.workspacescroll2.connect("scroll-event", self.on_test_scroll)

        self.add(self.workspacescroll2)
        self.show_all()

    def on_test_scroll(self, widget, event):
        if event.delta_x != 0:
            # Handle scroll value
            if self.scroll_value == 0:
                self.multiple = 1
                self.scroll_value += event.delta_x
            elif self.scroll_value < 0:
                self.scroll_value = (
                    0 if event.delta_x > 0 else self.scroll_value + event.delta_x
                )
            else:
                self.scroll_value = (
                    0 if event.delta_x < 0 else self.scroll_value + event.delta_x
                )

            # Do actual work
            if self.scroll_value >= 5 * self.multiple:
                self.multiple += 1
                print("I will do my command here")
            if self.scroll_value <= -5 * self.multiple:
                self.multiple += 1
                print("I will do my command here but negative")
        else:
            self.multiple = 1
            self.scroll_value = 0

    def on_scroll(self, widget, value):
        self.scroller.set_value(value)


# def apply_style(*args):
#     logger.info("[Bar] CSS applied")
# return set_stylesheet_from_file(get_relative_path("../bar/bar.css"))

if __name__ == "__main__":
    bar = Overview()
    # apply_style()
    fabric.start()
