import datetime
import json
import os
import shlex
import signal
import subprocess
from time import monotonic as time_now
from typing import Any, Callable, Literal, cast, get_args

from fabric.core.service import Property, Service, Signal
from fabric.utils import exec_shell_command_async
from gi.repository import Gio, GLib
from loguru import logger

from fabric_config.utils.hyprland_monitor import get_hyprland_monitors
from fabric_config.utils.hyprland_windows import hyprland_clients
from fabric_config.utils.process import run_command_async

RecordTarget = Literal["region", "window", "screen"]
RecordAudio = Literal["none", "desktop", "mic"]
SETTINGS_FILE = os.path.join(GLib.get_user_cache_dir(), "fabric", "screen_record.json")
THUMBNAIL_DIR = os.path.join(GLib.get_user_cache_dir(), "fabric", "screencasts")
# wf-recorder's --audio device: the default output's monitor, or the default
# input (wf-recorder's own default)
AUDIO_DEVICES: dict[RecordAudio, str | None] = {
    "none": None,
    "desktop": "@DEFAULT_MONITOR@",
    "mic": "@DEFAULT_SOURCE@",
}


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


def _window_boxes() -> str:
    """slurp boxes ("x,y wxh title") for the windows on the shown workspaces."""
    try:
        monitors = json.loads(get_hyprland_monitors().send_command("j/monitors").reply)
    except Exception as e:
        logger.error(f"[SCREENRECORD] Couldn't read monitors: {e}")
        return ""
    shown = {
        ws.get("id")
        for m in monitors
        for ws in (m.get("activeWorkspace"), m.get("specialWorkspace"))
        if ws and ws.get("id")
    }
    lines = []
    for c in hyprland_clients():
        if (c.get("workspace") or {}).get("id") not in shown or c.get("hidden"):
            continue
        (x, y), (w, h) = c.get("at", (0, 0)), c.get("size", (0, 0))
        if w > 0 and h > 0:
            title = (c.get("title") or c.get("class") or "").replace("\n", " ")
            lines.append(f"{x},{y} {w}x{h} {title}")
    return "\n".join(lines) + "\n"


def _load_settings() -> tuple[RecordTarget, RecordAudio]:
    try:
        with open(SETTINGS_FILE) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    target = data.get("target")
    audio = data.get("audio")
    return (
        cast(RecordTarget, target) if target in get_args(RecordTarget) else "region",
        cast(RecordAudio, audio) if audio in get_args(RecordAudio) else "none",
    )


class ScreenRecorder(Service):
    @Signal
    def recording(self, value: bool) -> None: ...

    def __init__(self, **kwargs):
        self.screenshot_path = GLib.get_home_dir() + "/Pictures/Screenshots"
        self.screenrecord_path = GLib.get_home_dir() + "/Videos/Screencasting/"
        self._current_screencast_path: str | None = None
        self._recorder: Gio.Subprocess | None = None
        # monotonic time the recording started, for the elapsed-time display
        self.recording_since: float | None = None
        self._target: RecordTarget
        self._audio: RecordAudio
        self._target, self._audio = _load_settings()

        super().__init__(**kwargs)

    @Property(str, "read-write", default_value="region")
    def target(self) -> str:
        """What a recording captures: "region", "window" or "screen"."""
        return self._target

    @target.setter
    def target(self, value: str):
        if value in get_args(RecordTarget) and value != self._target:
            self._target = cast(RecordTarget, value)
            self._save_settings()

    @Property(str, "read-write", default_value="none")
    def audio(self) -> str:
        """Sound to record along: "none", "desktop" (what's playing) or "mic"."""
        return self._audio

    @audio.setter
    def audio(self, value: str):
        if value in get_args(RecordAudio) and value != self._audio:
            self._audio = cast(RecordAudio, value)
            self._save_settings()

    def _save_settings(self):
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, "w") as f:
                json.dump({"target": self._target, "audio": self._audio}, f)
        except OSError as e:
            logger.error(f"[SCREENRECORD] Couldn't save settings: {e}")

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
                lambda file_path: self.send_screenshot_notification(
                    file_path=file_path if file_path else None,
                ),
            )

        except Exception:
            logger.error(f"[SCREENSHOT] Failed to run command: {command}")

    def screencast_start(self, fullscreen=False, target: str | None = None):
        """Record `target` (default: the saved one; `fullscreen` means "screen")."""
        if self.is_recording:
            logger.error(
                "[SCREENRECORD] Another instance of wf-recorder is already running"
            )
            return
        target = "screen" if fullscreen else target or self._target
        if target == "screen":
            # with several monitors wf-recorder asks which one on stdin, and
            # gives up; record the focused one
            self._start_wf_recorder(None, output=_focused_monitor())
            return

        # run slurp asynchronously so selecting a region doesn't block the UI;
        # for a window, it offers the windows' boxes and nothing else
        boxes = _window_boxes() if target == "window" else None
        try:
            slurp = Gio.Subprocess.new(
                ["slurp", "-r"] if boxes is not None else ["slurp"],
                Gio.SubprocessFlags.STDOUT_PIPE
                | Gio.SubprocessFlags.STDERR_SILENCE
                | (
                    Gio.SubprocessFlags.STDIN_PIPE
                    if boxes is not None
                    else Gio.SubprocessFlags.NONE
                ),
            )
        except GLib.Error as e:
            logger.error(f"[SCREENRECORD] Failed to start slurp: {e.message}")
            return

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

        slurp.communicate_utf8_async(boxes, None, on_slurp_done)

    def _start_wf_recorder(self, geometry: str | None, output: str | None = None):
        os.makedirs(self.screenrecord_path, exist_ok=True)
        time = datetime.datetime.today().strftime("%Y-%m-%d_%H-%M-%S")
        file_path = self.screenrecord_path + str(time) + ".mp4"
        command = ["wf-recorder", f"--file={file_path}", "--pixel-format", "yuv420p"]
        if geometry:
            command += ["-g", geometry]
        elif output:
            command += ["-o", output]
        if self._audio != "none":
            command.append(f"--audio={AUDIO_DEVICES[self._audio]}")
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

    def send_screencast_notification(self, file_path: str):
        # a frame from the video, shown in the notification
        os.makedirs(THUMBNAIL_DIR, exist_ok=True)
        thumbnail = os.path.join(
            THUMBNAIL_DIR, os.path.splitext(os.path.basename(file_path))[0] + ".png"
        )
        run_command_async(
            ["ffmpegthumbnailer", "-i", file_path, "-o", thumbnail, "-s", "512"],
            lambda ok, _out, _err: self._notify_screencast(
                file_path, thumbnail if ok and os.path.exists(thumbnail) else None
            ),
        )

    def _notify_screencast(self, file_path: str, thumbnail: str | None):
        cmd = [
            "notify-send",
            "-A",
            "view=Open",
            "-A",
            "files=Show in Files",
            "-A",
            "copy=Copy",
            "-i",
            "camera-video-symbolic",
            "-a",
            "Fabric Screenshot Utility",
        ]
        if thumbnail:
            cmd += ["-h", f"STRING:image-path:{thumbnail}"]
        cmd += ["Screencast Saved", os.path.basename(file_path)]

        def on_action(ok: bool, stdout: str, _err: str):
            if not ok:
                return
            match stdout.strip():
                case "view":
                    _spawn(["xdg-open", file_path])
                case "files":
                    _show_in_files(file_path)
                case "copy":
                    # as a file, so it pastes into chats and file managers
                    uri = GLib.filename_to_uri(file_path, None)
                    _spawn(["wl-copy", "--type", "text/uri-list", uri])

        run_command_async(cmd, on_action)

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


def _spawn(argv: list[str]):
    """Start and forget: no pipes, which a lingering child (wl-copy serving the
    clipboard, the app xdg-open starts) would hold open."""
    try:
        Gio.Subprocess.new(
            argv,
            Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE,
        )
    except GLib.Error as e:
        logger.error(f"[SCREENRECORD] Failed to start {argv[0]}: {e.message}")


def _show_in_files(file_path: str):
    """Open the folder with the file selected (FileManager1), or just the folder."""
    uri = GLib.filename_to_uri(file_path, None)

    def on_done(bus: Gio.DBusConnection, result: Gio.AsyncResult):
        try:
            bus.call_finish(result)
        except GLib.Error:
            _spawn(["xdg-open", os.path.dirname(file_path)])

    Gio.bus_get_sync(Gio.BusType.SESSION, None).call(
        "org.freedesktop.FileManager1",
        "/org/freedesktop/FileManager1",
        "org.freedesktop.FileManager1",
        "ShowItems",
        GLib.Variant("(ass)", ([uri], "")),
        None,
        Gio.DBusCallFlags.NONE,
        5000,
        None,
        on_done,
    )
