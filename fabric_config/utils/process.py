from typing import Callable

from gi.repository import Gio, GLib
from loguru import logger


def run_command_async(
    argv: list[str],
    callback: Callable[[bool, str, str], None] | None = None,
):
    """
    Run `argv` without a shell and call `callback(success, stdout, stderr)` once
    the process exits.

    Unlike `fabric.utils.exec_shell_command_async`, the callback fires even when
    the command prints nothing, and stderr is captured, so failures are visible.
    """
    try:
        process = Gio.Subprocess.new(
            argv,
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
        )
    except GLib.Error as e:
        logger.error(f"[PROCESS] Failed to start {argv[0]}: {e.message}")
        if callback:
            callback(False, "", e.message)
        return

    def on_done(proc: Gio.Subprocess, task: Gio.AsyncResult):
        try:
            _, stdout, stderr = proc.communicate_utf8_finish(task)
        except GLib.Error as e:
            if callback:
                callback(False, "", e.message)
            return
        if callback:
            callback(proc.get_successful(), stdout or "", stderr or "")

    process.communicate_utf8_async(None, None, on_done)
