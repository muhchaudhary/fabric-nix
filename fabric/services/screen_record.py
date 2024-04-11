import asyncio
import datetime
import subprocess

from fabric.service import Service
from fabric.utils import exec_shell_command
from gi.repository import GLib
from loguru import logger


def exec_shell_command_async(cmd: str) -> bool:
    if isinstance(cmd, str):
        try:
            GLib.spawn_command_line_async(cmd)
            return True
        except ValueError:
            return False
    else:
        return False


class ScreenRecorder(Service):
    # __gsignals__ = SignalContainer(

    # )
    def __init__(self, **kwargs):
        self.screenshot_path = GLib.get_home_dir() + "/Pictures/Screenshots/"
        self.screenrecord_path = GLib.get_home_dir() + "/Videos/Screencasting/"
        self.recording = False
        super().__init__(**kwargs)

    def screenshot(self, fullscreen=False, save_copy=True):
        time = datetime.datetime.today().strftime("%Y-%m-%d_%H-%M-%S")
        file_path = self.screenshot_path + str(time) + ".png"
        command = ["wayshot", "-f", file_path] if save_copy else ["wayshot", "--stdout"]

        if not fullscreen:
            region = exec_shell_command("slurp").split("\n")
            if region[0] == "selection cancelled":
                return
            command = command + ["-s", region[0]]

        wayshot = subprocess.run(command, check=True, capture_output=True)
        if save_copy:
            exec_shell_command_async(f"bash -c 'wl-copy < {file_path}' ")
            asyncio.run(self.send_screenshot_notification_file("file",file_path))
            return
        subprocess.run(["wl-copy"], input=wayshot.stdout)
        asyncio.run(self.send_screenshot_notification_file("stdout"))

    def screencast_start(self, fullscreen=False):
        time = datetime.datetime.today().strftime("%Y-%m-%d_%H-%M-%S")
        file_path = self.screenrecord_path + str(time) + ".mp4"
        area = ""
        if fullscreen:
            area = exec_shell_command("slurp")
        command = f"wf-recorder -g {area} -f {file_path}"

        exec_shell_command_async(command)
        pass

    def screencast_stop(self):
        exec_shell_command_async("killall -INT wf-recorder")
        self.recording = False

    async def send_screenshot_notification_file(self, notify_type, file_path = None):
        cmd = (
            "notify-send "
            + "-A 'files=Show in Files' "
            + "-A 'view=View' "
            + f"-A 'edit=Edit' -i {file_path} "
            + f" Screenshot {file_path}"
        ) if notify_type == "file" else "notify-send 'Screenshot Sent to Clipboard'"
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        out = stdout.decode().strip("\n")
        print(out)
        if stderr:
            logger.error("Failed to send notification")
        if out == "files":
            exec_shell_command_async(f"xdg-open {self.screenshot_path}")
        elif out == "view":
            exec_shell_command_async(f"xdg-open {file_path}")
        elif out == "edit":
            exec_shell_command_async(f"swappy -f {file_path}")
