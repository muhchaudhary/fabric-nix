import fabric
import os
from fabric.utils import (
    set_stylesheet_from_file,
    get_relative_path,
    monitor_file
)
from bar.bar import StatusBar
# from overview.overview import Overview
from loguru import logger

PYWAL = True


def apply_style(*args):
    logger.info("[Main] CSS applied")
    return set_stylesheet_from_file(get_relative_path("style/main.css"))


if __name__ == "__main__":
    bar = StatusBar()
    # overview = Overview()

    if PYWAL is True:
        monitor = monitor_file(
            f"/home/{os.getlogin()}/.cache/wal/colors.css", "none"
        )
        monitor.connect("changed", apply_style)

    # initialize style
    apply_style()

    fabric.start()