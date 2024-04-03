from loguru import logger

import fabric
from fabric.utils import (
    get_relative_path,
    set_stylesheet_from_file,
)
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.date_time import DateTime
from fabric.widgets.wayland import Window

PYWAL = False
CIRCULAR_PROG_SIZE = 150


class ClockWidget(Window):
    def __init__(self, **kwargs):
        self.center_box = CenterBox(name="clock-window")

        self.main_box = Box(
            name="clockbox",
            children=[
                DateTime(format_list=["%A %B %d"], name="date", interval=10000),
                DateTime(format_list=["%I:%M %p"], name="clock"),
            ],
            orientation="v",
        )

        self.center_box.add_center(self.main_box)

        super().__init__(
            layer="bottom",
            anchor="left top right",
            margin="100px 0px 0px 0px",
            all_visible=True,
            exclusive=False,
            children=self.center_box,
        )

        self.show_all()

    # def update_progress_bars(self):
    #     self.ram_circular_progress_bar.percentage = psutil.virtual_memory().percent
    #     self.cpu_circular_progress_bar.percentage = psutil.cpu_percent()
    #     self.battery_circular_progress_bar.percentage = psutil.sensors_battery().percent
    #     return True


def apply_style(*args):
    logger.info("[Desktop Widget] CSS applied")
    return set_stylesheet_from_file(get_relative_path("desktop_widget.css"))


if __name__ == "__main__":
    desktop_widget = ClockWidget()

    # apply_style()

    # monitor = monitor_file(get_relative_path("desktop_widget.css"))
    # monitor.connect("changed", apply_style)

    fabric.start()
