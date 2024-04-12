from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.date_time import DateTime
from fabric.widgets.wayland import Window


class ClockWidget(Window):
    def __init__(self, **kwargs):
        self.center_box = CenterBox(name="clock-window")

        self.main_box = Box(
            name="clockbox",
            children=[
                DateTime(format_list=["%I:%M"], name="clock"),
                DateTime(format_list=["%A %B %d"], name="date", interval=10000),
            ],
            orientation="v",
        )

        self.center_box.add_center(self.main_box)

        super().__init__(
            layer="bottom",
            anchor="left top right",
            # margin="100px 0px 0px 0px",
            all_visible=True,
            exclusive=False,
            children=self.center_box,
        )

        self.show_all()
