
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.datetime import DateTime
from fabric.widgets.wayland import WaylandWindow


class ClockWidget(WaylandWindow):
    def __init__(self, **kwargs):
        self.center_box = CenterBox(name="clock-window")

        self.main_box = Box(
            name="clockbox",
            children=[
                DateTime(formatters=("%I:%M %p"), name="clock"),
                DateTime(formatters=("%A %B %d"), name="date", interval=10000),
            ],
            orientation="v",
        )

        # self.center_box.add_center(self.main_box)

        super().__init__(
            layer="bottom",
            anchor="left top right",
            all_visible=True,
            exclusive=False,
            child=self.main_box,
        )

        self.show_all()


