import datetime
import json
import os
import shlex
import signal
import subprocess
from time import monotonic as time_now
from typing import Any, Callable

from fabric.core.service import Property, Service, Signal
from fabric.utils import exec_shell_command_async
from gi.repository import Gio, GLib
from loguru import logger

from fabric_config.utils.hyprland_monitor import get_hyprland_monitors


def exec_shell_command_async_ignore_stdout(
    cmd: str | list[str],
    callback: Callable[[str], Any] | None = None,
) -> tuple[Gio.Subprocess | None, Gio.DataInputStream]:
    """
    executes a shell command and returns the output asynchronously

    :param cmd: the shell command to execute
    :type cmd: str
    :param callback: a function to retrieve the result at or `None` to ignore the result
    :type callback: Callable[[str], Any] | None, optional
    :return: a Gio.Subprocess object which holds a reference to your process and a Gio.DataInputStream object for stdout
    :rtype: tuple[Gio.Subprocess | None, Gio.DataInputStream]
    """
    process = Gio.Subprocess.new(
        shlex.split(cmd) if isinstance(cmd, str) else cmd,  # type: ignore
        Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,  # type: ignore
    )

    stdout = Gio.DataInputStream(
        base_stream=process.get_stdout_pipe(),  # type: ignore
        close_base_stream=True,
    )

    def reader_loop(stdout: Gio.DataInputStream):
        def read_line(stream: Gio.DataInputStream, res: Gio.AsyncResult):
            output, *_ = stream.read_line_finish(res)
            if isinstance(output, bytes):
                callback(output.decode()) if callback else None

        stdout.read_line_async(GLib.PRIORITY_DEFAULT, None, read_line)

    reader_loop(stdout)

    return process, stdout


def _focused_monitor() -> str | None:
    try:
        monitors = json.loads(get_hyprland_monitors().send_command("j/monitors").reply)
    except Exception as e:
        logger.error(f"[SCREENRECORD] Couldn't read monitors: {e}")
        return None
    return next((m["name"] for m in monitors if m.get("focused")), None)


class ScreenRecorder(Service):
    @Signal
    def recording(self, value: bool) -> None: ...

    @Signal
    def screenshot_taken(self, path: str) -> None:
        """A screenshot was saved ("" when it only went to the clipboard)."""

    def __init__(self, **kwargs):
        self.screenshot_path = GLib.get_home_dir() + "/Pictures/Screenshots"
        self.screenrecord_path = GLib.get_home_dir() + "/Videos/Screencasting/"
        self._current_screencast_path: str | None = None
        self._recorder: Gio.Subprocess | None = None
        # monotonic time the recording started, for the elapsed-time display
        self.recording_since: float | None = None

        super().__init__(**kwargs)

    def screenshot(self, fullscreen=False, save_copy=True):
        time = datetime.datetime.today().strftime("%Y-%m-%d_%H-%M-%S")
        command = (
            [
                "hyprshot",
                "-s",
                "-o",
                self.screenshot_path,
                "-f",
                f"{str(time)}_fabric_screenshot.png",
            ]
            if save_copy
            else ["hyprshot", "-s", "--clipboard-only"]
        )
        command.extend(
            ["-m", "active", "-m", "output"] if fullscreen else ["-m", "region"]
        )
        command.append("-- ls")  # This is so there is something in stdout
        try:
            exec_shell_command_async_ignore_stdout(
                " ".join(command),
                lambda file_path: (
                    self.send_screenshot_notification(
                        file_path=file_path if file_path else None,
                    ),
                    self.screenshot_taken(file_path or ""),
                ),
            )

        except Exception:
            logger.error(f"[SCREENSHOT] Failed to run command: {command}")

    def screencast_start(self, fullscreen=False):
        if self.is_recording:
            logger.error(
                "[SCREENRECORD] Another instance of wf-recorder is already running"
            )
            return
        if fullscreen:
            # with several monitors wf-recorder asks which one on stdin, and
            # gives up; record the focused one
            self._start_wf_recorder(None, output=_focused_monitor())
            return

        # run slurp asynchronously so selecting a region doesn't block the UI
        slurp = Gio.Subprocess.new(
            ["slurp"],
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE,
        )

        def on_slurp_done(process: Gio.Subprocess, task: Gio.Task):
            try:
                _, stdout, _ = process.communicate_utf8_finish(task)
            except GLib.Error as e:
                logger.error(f"[SCREENRECORD] slurp failed: {e.message}")
                return
            geometry = (stdout or "").strip()
            if not process.get_successful() or not geometry:
                logger.info("[SCREENRECORD] Region selection cancelled")
                return
            self._start_wf_recorder(geometry)

        slurp.communicate_utf8_async(None, None, on_slurp_done)

    def _start_wf_recorder(self, geometry: str | None, output: str | None = None):
        os.makedirs(self.screenrecord_path, exist_ok=True)
        time = datetime.datetime.today().strftime("%Y-%m-%d_%H-%M-%S")
        file_path = self.screenrecord_path + str(time) + ".mp4"
        command = ["wf-recorder", f"--file={file_path}", "--pixel-format", "yuv420p"]
        if geometry:
            command += ["-g", geometry]
        elif output:
            command += ["-o", output]
        try:
            # wf-recorder writes progress continuously; don't pipe its output, or
            # the unread pipe fills up and stalls the recording
            recorder = Gio.Subprocess.new(
                command,
                Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE,
            )
        except GLib.Error as e:
            logger.error(f"[SCREENRECORD] Failed to start wf-recorder: {e.message}")
            return
        self._recorder = recorder
        self._current_screencast_path = file_path
        self.recording_since = time_now()
        # however it ends (stopped here, killed, crashed), finish up then
        recorder.wait_async(None, self._on_recorder_exit)
        self.emit("recording", True)

    def screencast_stop(self):
        if self._recorder is not None:
            # SIGINT lets wf-recorder finish writing the file
            self._recorder.send_signal(signal.SIGINT)
        else:
            # one started outside fabric
            exec_shell_command_async("killall -INT wf-recorder")
            self.emit("recording", False)

    def _on_recorder_exit(self, recorder: Gio.Subprocess, task: Gio.AsyncResult):
        try:
            recorder.wait_finish(task)
        except GLib.Error as e:
            logger.error(f"[SCREENRECORD] Waiting for wf-recorder failed: {e.message}")
        if recorder is not self._recorder:
            return
        self._recorder = None
        self.recording_since = None
        self.emit("recording", False)
        if self._current_screencast_path is None:
            return
        if os.path.exists(self._current_screencast_path):
            self.send_screencast_notification(self._current_screencast_path)
        else:
            logger.error("[SCREENRECORD] wf-recorder exited without saving a file")
        self._current_screencast_path = None

    def send_screencast_notification(self, file_path):
        # TODO: Generate a thumbnail
        # exec_shell_command_async(f"totem-video-thumbnailer {file_path} {FABRIC_CACHE}")

        cmd = ["notify-send"]
        cmd.extend(
            [
                "-A",
                "files=Show in Files",
                "-A",
                "view=View",
                "-i",
                "camera-video-symbolic",
                "-a",
                "Fabric Screenshot Utility",
                "Screencast Saved",
                f"Saved Screencast at {file_path}",
            ]
        )

        proc: Gio.Subprocess = Gio.Subprocess.new(cmd, Gio.SubprocessFlags.STDOUT_PIPE)

        def do_callback(process: Gio.Subprocess, task: Gio.Task):
            try:
                _, stdout, _ = process.communicate_utf8_finish(task)
            except GLib.Error as e:
                logger.error(
                    f"[SCREENCAST] Failed read notification action with error {e.message}"
                )
                return

            match (stdout or "").strip("\n"):
                case "files":
                    exec_shell_command_async(f"xdg-open {self.screenrecord_path}")
                case "view":
                    exec_shell_command_async(f"xdg-open {file_path}")

        proc.communicate_utf8_async(None, None, do_callback)

    def send_screenshot_notification(self, file_path=None):
        cmd = ["notify-send"]
        cmd.extend(
            [
                "-A",
                "files=Show in Files",
                "-A",
                "view=View",
                "-A",
                "edit=Edit",
                "-i",
                "camera-photo-symbolic",
                "-a",
                "Fabric Screenshot Utility",
                "-h",
                f"STRING:image-path:{file_path}",
                "Screenshot Saved",
                f"Saved Screenshot at {file_path}",
            ]
            if file_path
            else ["Screenshot Sent to Clipboard"]
        )

        proc: Gio.Subprocess = Gio.Subprocess.new(cmd, Gio.SubprocessFlags.STDOUT_PIPE)

        def do_callback(process: Gio.Subprocess, task: Gio.Task):
            try:
                _, stdout, _ = process.communicate_utf8_finish(task)
            except GLib.Error as e:
                logger.error(
                    f"[SCREENSHOT] Failed read notification action with error {e.message}"
                )
                return

            match (stdout or "").strip("\n"):
                case "files":
                    exec_shell_command_async(f"xdg-open {self.screenshot_path}")
                case "view":
                    exec_shell_command_async(f"xdg-open {file_path}")
                case "edit":
                    exec_shell_command_async(f"swappy -f {file_path}")

        proc.communicate_utf8_async(None, None, do_callback)

    @Property(bool, "readable", default_value=False)
    def is_recording(self) -> bool:
        if self._recorder is not None:
            return True
        # exec_shell_command returns False (not "") when it fails, and stderr
        # output when pidof finds nothing, so use the exit status instead
        return subprocess.run(["pidof", "-q", "wf-recorder"]).returncode == 0
