from fabric_config.components.overview import Overview
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


def apply_style(app: Application):
    logger.info("[Main] CSS applied")
    return app.set_stylesheet_from_file(get_relative_path("style/main.css"))


sc = config.sc

screen_corners = ScreenCorners()

logger.disable("fabric.hyprland.widgets")
bar = StatusBarSeperated()
clockWidget = ClockWidget()
overview = Overview()
systemOverlay = SystemOSD()
nc = NotificationPopup()
appMenu = AppMenu()

file = monitor_file(get_relative_path("style/main.css"))
_ = file.connect("changed", lambda *_: apply_style(app))

app = Application(
    "fabric-bar",
    bar,
    clockWidget,
    systemOverlay,
    nc,
    appMenu,
    overview,
)
apply_style(app)


def main():
    app.run()


if __name__ == "__main__":
    main()
