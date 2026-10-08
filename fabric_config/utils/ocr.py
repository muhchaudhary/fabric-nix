"""
Copy the text in a region of the screen: slurp to select it, grim to
capture it, tesseract to read it, wl-copy to put it on the clipboard (so it
lands in the clipboard history too).
"""

import os
import tempfile

from gi.repository import GLib
from loguru import logger

from fabric_config.utils.process import run_command_async

# tesseract reads small UI text much better scaled up, but large text
# (a selection over a heading or a clock) worse
SCALE = 2
SCALE_UP_BELOW = 300  # px: selections shorter than this are scaled up
LANGUAGE = os.environ.get("FABRIC_OCR_LANG", "eng")
PREVIEW_CHARS = 120


def _notify(summary: str, body: str = "", icon: str = "edit-copy-symbolic"):
    run_command_async(
        [
            "notify-send",
            "-a",
            "Copy Text",
            "-i",
            icon,
            summary,
            *([body] if body else []),
        ]
    )


def copy_text_from_region(delay_ms: int = 0):
    """Select a region, read its text and copy it.

    `delay_ms` gives a closing popup time to leave the screen first.
    """
    if GLib.find_program_in_path("tesseract") is None:
        _notify("Copy text needs tesseract", icon="dialog-warning-symbolic")
        return
    fd, image = tempfile.mkstemp(prefix="fabric-ocr-", suffix=".png")
    os.close(fd)

    def cleanup():
        try:
            os.unlink(image)
        except OSError:
            pass

    def on_text(success: bool, stdout: str, stderr: str):
        cleanup()
        text = stdout.strip()
        if not success:
            logger.warning(f"[OCR] tesseract: {stderr.strip()}")
            _notify("Couldn't read the text", icon="dialog-warning-symbolic")
            return
        if not text:
            _notify("No text found", icon="dialog-information-symbolic")
            return
        run_command_async(["wl-copy", "--", text])
        words = len(text.split())
        preview = " ".join(text.split())
        if len(preview) > PREVIEW_CHARS:
            preview = preview[: PREVIEW_CHARS - 1] + "…"
        _notify(f"Copied {words} word{'s' if words != 1 else ''}", preview)

    def on_captured(success: bool, _stdout: str, stderr: str):
        if not success:
            cleanup()
            logger.warning(f"[OCR] grim: {stderr.strip()}")
            _notify("Couldn't capture the screen", icon="dialog-warning-symbolic")
            return
        run_command_async(["tesseract", image, "-", "-l", LANGUAGE], on_text)

    def on_region(success: bool, stdout: str, _stderr: str):
        region = stdout.strip()
        if not success or not region:
            cleanup()  # Escape cancels slurp; nothing to report
            return
        try:
            height = int(region.split()[1].split("x")[1])
        except (IndexError, ValueError):
            height = 0
        scale = SCALE if 0 < height < SCALE_UP_BELOW else 1
        run_command_async(["grim", "-s", str(scale), "-g", region, image], on_captured)

    def start():
        run_command_async(["slurp"], on_region)
        return False

    if delay_ms:
        GLib.timeout_add(delay_ms, start)
    else:
        start()
