import fabric
from fabric.utils import set_stylesheet_from_file, get_relative_path, monitor_file
from components.bar.bar import StatusBar
from components.desktop.desktop_widget import ClockWidget
from components.quick_settings.quick_settings import AudioOverlay
import gi


# from overview.overview import Overview
from loguru import logger


def apply_style(*args):
    logger.info("[Main] CSS applied")
    return set_stylesheet_from_file(get_relative_path("style/main.css"))


if __name__ == "__main__":
    logger.disable("fabric.hyprland.widgets")
    logger.disable("fabric.audio.service")
    bar = StatusBar()
    clockWidget = ClockWidget()
    audioOverlay = AudioOverlay()

    apply_style()

    fabric.start()
