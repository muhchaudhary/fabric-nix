import fabric
import os
from fabric.utils import set_stylesheet_from_file, get_relative_path, monitor_file
from components.bar.bar import StatusBar
from components.desktop.desktop_widget import ClockWidget
from widgets.popup_window import PopupWindow
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

# from overview.overview import Overview
from loguru import logger

PYWAL = True


def apply_style(*args):
    logger.info("[Main] CSS applied")
    return set_stylesheet_from_file(get_relative_path("style/main.css"))


if __name__ == "__main__":
    logger.disable("fabric.hyprland.widgets")
    logger.disable("fabric.audio.service")
    bar = StatusBar()
    clockWidget = ClockWidget()
    # overview = Overview()
    # bt = BluetoothWidget()

    if PYWAL is True:
        monitor = monitor_file(get_relative_path("style/main.css"))
        monitor.connect("changed", apply_style)

    # initialize style
    apply_style()

    fabric.start()
