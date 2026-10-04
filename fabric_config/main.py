import subprocess
import os
from fabric import Application
from fabric.utils import get_relative_path
from loguru import logger

import fabric_config.config as config

from fabric_config.components import (
    AppMenu,
    DesktopManager,
    NotificationPopup,
    StatusBarSeperated,
    SystemOSD,
)
from fabric_config.components.bar.bar import ScreenCorners
from fabric_config.components.bar.widgets.notification_center import (
    NotificationCenterPopup,
)
from fabric_config.components.overview import Overview

from fabric_config.components.dock import AppDock
from fabric_config.components.radial_menu import RadialItem, RadialMenu
from fabric_config.components.wallpaper_picker import wallpaper_picker

from gi.repository import GLib

from fabric_config.utils.color_picker import pick_color
from fabric_config.utils.cursors import install_pointer_cursors
from fabric_config.utils.process import run_command_async

CACHE_DIR = str(GLib.get_user_cache_dir()) + "/fabric"
CSS_CACHE = CACHE_DIR + "/css"
CSS_PATH = CSS_CACHE + "/main.css"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
if not os.path.exists(CSS_CACHE):
    os.makedirs(CSS_CACHE)


class MyApp(Application):
    def __init__(self):
        # a hand cursor over every button, before any window is built
        install_pointer_cursors()
        self.sc = config.sc
        self.screen_corners = ScreenCorners()
        self.bar = StatusBarSeperated()
        self.desktop = DesktopManager()
        self.overview = Overview()
        self.systemOverlay = SystemOSD()
        self.nc = NotificationPopup()
        self.appMenu = AppMenu()
        self.dock = AppDock()
        self.wallpaper_picker = wallpaper_picker
        self.radial_menu = RadialMenu(self._radial_items())
        super().__init__(
            "fabric-bar",
            self.bar,
            *self.desktop.windows,
            *self.desktop.player_windows,
            self.systemOverlay,
            self.nc,
            self.appMenu,
            self.overview,
            self.dock,
            self.radial_menu,
        )
        config.theme.connect("notify::is-light", lambda *_: self.apply_style())
        self.apply_style()

    def _radial_items(self) -> list[RadialItem]:
        return [
            RadialItem(
                "Apps", "view-app-grid-symbolic", lambda: self.appMenu.toggle_popup()
            ),
            RadialItem(
                "Overview",
                "focus-windows-symbolic",
                lambda: self.overview.toggle_popup(),
            ),
            RadialItem(
                "Screenshot", "camera-photo-symbolic", lambda: self.sc.screenshot()
            ),
            RadialItem(
                "Record",
                "media-record-symbolic",
                lambda: (
                    self.sc.screencast_stop()
                    if self.sc.is_recording
                    else self.sc.screencast_start()
                ),
            ),
            RadialItem("Colour", "color-select-symbolic", lambda: pick_color()),
            RadialItem(
                "Wallpaper",
                "preferences-desktop-wallpaper-symbolic",
                lambda: config.wallpaper_slideshow.next(),
            ),
            RadialItem(
                "Caffeine",
                "my-caffeine-on-symbolic",
                lambda: setattr(config.caffeine, "active", not config.caffeine.active),
            ),
            RadialItem(
                "Lock",
                "system-lock-screen-symbolic",
                lambda: run_command_async(["loginctl", "lock-session"]),
            ),
        ]

    def apply_style(self):
        logger.info("[Main] Compiling SCSS and applying style")
        scss_name = (
            "style/main-light.scss" if config.theme.is_light else "style/main.scss"
        )
        scss = get_relative_path(scss_name)
        subprocess.run(["sass", str(scss), CSS_PATH], check=True)
        return self.set_stylesheet_from_file(CSS_PATH)


the_app = MyApp()


def main():
    @the_app.action()
    def toggle_appmenu():
        the_app.appMenu.toggle_popup()

    @the_app.action()
    def toggle_radial_menu():
        the_app.radial_menu.toggle()

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
    def toggle_notification_center():
        NotificationCenterPopup.toggle_popup()

    @the_app.action()
    def toggle_do_not_disturb():
        config.notifications.dnd = not config.notifications.dnd

    @the_app.action()
    def toggle_wallpaper_picker():
        the_app.wallpaper_picker.toggle_popup()

    @the_app.action()
    def stop_adhan():
        from fabric_config.components.bar.widgets.prayer_times import (
            _get_prayer_service,
        )

        _get_prayer_service().adhan.stop()

    @the_app.action()
    def preview_weather(kind: str = ""):
        """Show a weather effect on the desktop for 30 s (rain, snow, storm, ...)."""
        the_app.desktop.preview_weather(kind)

    @the_app.action()
    def quit():
        logger.info("[Main] Quitting application")
        the_app.quit()

    @the_app.action()
    def apply_style():
        logger.info("[Main] Applying new style")
        the_app.apply_style()

    the_app.run()


if __name__ == "__main__":
    main()
