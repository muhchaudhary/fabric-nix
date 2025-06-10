from fabric import Application
from fabric.utils import get_relative_path, monitor_file
from loguru import logger

import fabric_config.config as config
from fabric_config.components import (
    AppMenu,
    ClockWidget,
    NotificationPopup,
    StatusBarSeperated,
    SystemOSD,
)
from fabric_config.components.bar.bar import ScreenCorners
from fabric_config.components.overview import Overview


class MyApp(Application):
    def __init__(self):
        self.sc = config.sc
        self.screen_corners = ScreenCorners()
        self.bar = StatusBarSeperated()
        self.clockWidget = ClockWidget()
        self.overview = Overview()
        self.systemOverlay = SystemOSD()
        self.nc = NotificationPopup()
        self.appMenu = AppMenu()
        super().__init__(
            "fabric-bar",
            self.bar,
            self.clockWidget,
            self.systemOverlay,
            self.nc,
            self.appMenu,
            self.overview,
        )
        self.apply_style()
        file = monitor_file(get_relative_path("style/colors.css"))
        _ = file.connect("changed", lambda *_: self.apply_style())

    def apply_style(self):
        logger.info("[Main] CSS applied")
        return self.set_stylesheet_from_file(get_relative_path("style/main.css"))


def main():
    the_app = MyApp()

    @the_app.action()
    def toggle_appmenu():
        the_app.appMenu.toggle_popup()

    @the_app.action()
    def toggle_overview():
        the_app.overview.toggle_popup()

    @the_app.action()
    def take_screenshot(fullscreen=False):
        return the_app.sc.screenshot(fullscreen)

    @the_app.action()
    def start_screencast(fullscreen=False):
        return the_app.sc.screencast_start(fullscreen)

    @the_app.action()
    def stop_screencast():
        return the_app.sc.screencast_stop()

    @the_app.action()
    def toggle_system_osd(osd_type: str):
        the_app.systemOverlay.enable_popup(osd_type)
    
    @the_app.action()
    def quit():
        logger.info("[Main] Quitting application")
        the_app.quit()

    the_app.run()


if __name__ == "__main__":
    main()
