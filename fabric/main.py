import fabric
import config
from fabric.utils import set_stylesheet_from_file, get_relative_path
from components.bar.bar import StatusBar
from components.desktop.desktop_widget import ClockWidget
from components.OSD.SystemOSD import SystemOSD


# from overview.overview import Overview
from loguru import logger


def apply_style(*args):
    logger.info("[Main] CSS applied")
    return set_stylesheet_from_file(get_relative_path("style/main.css"))


if __name__ == "__main__":
    bar = StatusBar()
    clockWidget = ClockWidget()
    systemOverlay = SystemOSD()

    # For system shortcuts
    sc = config.sc

    apply_style()

    fabric.start()
