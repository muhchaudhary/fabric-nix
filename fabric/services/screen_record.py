from fabric.service import Service, Signal, SignalContainer
from gi.repository import GLib
from fabric.utils import exec_shell_command
import datetime


class ScreenRecorder(Service):
    # __gsignals__ = SignalContainer(

    # )
    def __init__(self, **kwargs):
        self.screenshot_path = GLib.get_home_dir() + "/Pictures/Screenshots/"
        self.screenrecord_path = GLib.get_home_dir() + "/Videos/Screencasting/"
        super().__init__(**kwargs)

    def screenshot(self, fullscreen=False):
        time = datetime.datetime.today().strftime("%Y-%m-%d_%H-%M-%S")
        file_path = self.screenshot_path + str(time) + ".png"
        command = f"wayshot -f {file_path}"
        if not fullscreen:
            command += f" -s \"{exec_shell_command('slurp')}\" "
        print(command)
        exec_shell_command(command)

    def screen_record(self, fullscreen = False):
        pass