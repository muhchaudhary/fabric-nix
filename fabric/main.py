import config
from components.app_menu.app_menu import appMenu
from components.bar.bar import StatusBar
from components.desktop.desktop_widget import ClockWidget
from components.osd.system_osd import SystemOSD

# from overview.overview import Overview
from loguru import logger

import fabric
from fabric.utils import get_relative_path, monitor_file, set_stylesheet_from_file


def apply_style(*args):
    logger.info("[Main] CSS applied")
    return set_stylesheet_from_file(get_relative_path("style/main.css"))


if __name__ == "__main__":
    logger.disable("fabric.hyprland.widgets")
    logger.disable("components.bar.widgets.date_time")
    bar = StatusBar()
    clockWidget = ClockWidget()
    systemOverlay = SystemOSD()
    appMenu = appMenu

    file = monitor_file(get_relative_path("style/main.css"))
    file.connect("changed", lambda *args: apply_style())
    # For system shortcuts
    sc = config.sc

    apply_style()

    fabric.start()
