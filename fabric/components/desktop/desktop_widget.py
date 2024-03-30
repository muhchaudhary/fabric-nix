import fabric
import os
import psutil
from loguru import logger
from fabric.widgets.box import Box
from fabric.widgets.wayland import Window
from fabric.widgets.date_time import DateTime
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.overlay import Overlay
from fabric.widgets.label import Label
from fabric.widgets.circular_progress_bar import CircularProgressBar
from fabric.utils import (
    set_stylesheet_from_file,
    invoke_repeater,
    monitor_file,
    get_relative_path,
)

PYWAL = False
CIRCULAR_PROG_SIZE = 150

class ClockWidget(Window):
    def __init__(self, **kwargs):
        self.center_box = CenterBox(name="clock-window")

        self.main_box = Box(
            name = "clockbox",
            children=[
                DateTime(format_list=["%A. %d %B"], name="date", interval=10000),
                DateTime(format_list=["%I:%M"], name="clock"),
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
            children=self.center_box
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

