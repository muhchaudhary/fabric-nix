import fabric
import gi
from fabric.utils import get_relative_path, monitor_file, set_stylesheet_from_file
from loguru import logger

import config
from components.app_menu.app_menu import appMenu
from components.bar.bar import StatusBar
from components.desktop.desktop_widget import ClockWidget
from components.osd.system_osd import SystemOSD
from components.notifications.notification_popup import NotificationPopup

from services.notifications_astal_v2 import NotificationServer

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402


def apply_style(*args):
    logger.info("[Main] CSS applied")
    return set_stylesheet_from_file(get_relative_path("style/main.css"))

def quit_fabric():
    Gtk.main_quit()

if __name__ == "__main__":
    logger.disable("fabric.hyprland.widgets")
    logger.disable("components.bar.widgets.date_time")
    bar = StatusBar()
    clockWidget = ClockWidget()
    systemOverlay = SystemOSD()
    nc = NotificationPopup(NotificationServer())
    appMenu = appMenu

    file = monitor_file(get_relative_path("style/main.css"))
    file.connect("changed", lambda *args: apply_style())
    # For system shortcuts
    sc = config.sc

    apply_style()

    fabric.start()

