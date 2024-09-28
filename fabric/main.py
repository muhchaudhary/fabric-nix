from fabric import Application
import gi
from fabric.utils import get_relative_path, monitor_file
from loguru import logger

import config
from components.app_menu.app_menu import AppMenu
from components.bar.bar import StatusBar
from components.desktop.desktop_widget import ClockWidget
from components.osd.system_osd import SystemOSD
from components.notifications.notification_popup import NotificationPopup



def apply_style(app: Application):
    logger.info("[Main] CSS applied")
    return app.set_stylesheet_from_file(get_relative_path("style/main.css"))





if __name__ == "__main__":
    logger.disable("fabric.hyprland.widgets")
    bar = StatusBar()
    clockWidget = ClockWidget()
    systemOverlay = SystemOSD()
    nc = NotificationPopup(config.notification_server)
    appMenu = AppMenu()
    sc = config.sc

    file = monitor_file(get_relative_path("style/main.css"))
    file.connect("changed", lambda *args: apply_style(app))

    app = Application("fabric-bar")
    apply_style(app)

    def quit_fabric():
        app.quit()

    app.run()

    # For system shortcuts
