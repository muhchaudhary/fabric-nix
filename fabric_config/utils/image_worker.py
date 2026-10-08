"""
One worker thread for decoding images: wallpapers (accent colour, the
desktop's legibility map, slideshow brightness) and album covers.

A 4K PNG decodes to tens of MB. Done on a thread per job, every monitor and
every service decoded the same wallpaper at once, each in its own glibc arena,
and glibc kept those arenas' freed memory: ~80 MB of RSS that never went away.
Here jobs run one at a time, a wallpaper is decoded once and kept (reduced)
for the jobs that follow, and freed memory is handed back to the OS once the
queue goes idle.
"""

import ctypes
import os
import queue
import threading
from collections.abc import Callable
from typing import Any

from gi.repository import GLib
from loguru import logger
from PIL import Image

# longest side wallpapers are kept at: well above what any measurement needs
# (the legibility map works at 1024 px across)
REDUCED_SIDE = 2048
# keep the last decoded image this long after the queue goes idle, so
# measurements that follow one another (accent, then each monitor's map)
# share one decode
LINGER_S = 30

_jobs: queue.SimpleQueue = queue.SimpleQueue()
_thread: threading.Thread | None = None
_lock = threading.Lock()
# (path, mtime) -> RGB image, only touched on the worker thread
_decoded: dict[tuple[str, float], Image.Image] = {}

try:
    _malloc_trim = ctypes.CDLL("libc.so.6").malloc_trim
except (OSError, AttributeError):
    _malloc_trim = None


def submit(work: Callable[[], Any], callback: Callable[[Any], Any] | None = None):
    """Run `work` on the image thread; `callback(result)` on the main loop
    (`None` if it raised)."""
    global _thread
    with _lock:
        if _thread is None:
            _thread = threading.Thread(target=_run, name="image-worker", daemon=True)
            _thread.start()
    _jobs.put((work, callback))


def open_reduced(path: str) -> Image.Image:
    """
    `path` as RGB, at most REDUCED_SIDE on its longest side. Call it from
    `submit`ted work only: the same file is decoded once and shared. Don't
    modify the result.
    """
    key = (path, os.path.getmtime(path))
    if (image := _decoded.get(key)) is not None:
        return image
    _decoded.clear()
    with Image.open(path) as source:
        # JPEGs decode straight to a reduced size; other formats decode in
        # full, so shrink before converting rather than converting full size
        source.draft("RGB", (REDUCED_SIDE, REDUCED_SIDE))
        source.thumbnail((REDUCED_SIDE, REDUCED_SIDE), Image.Resampling.BOX)
        image = source.convert("RGB")
    _decoded[key] = image
    return image


def _trim():
    if _malloc_trim is not None:
        _malloc_trim(0)


def _run():
    while True:
        try:
            work, callback = _jobs.get(timeout=LINGER_S)
        except queue.Empty:
            if _decoded:
                _decoded.clear()
                _trim()
            continue
        try:
            result = work()
        except Exception as e:
            logger.warning(f"[ImageWorker] {e}")
            result = None
        if callback is not None:
            GLib.idle_add(lambda cb=callback, r=result: cb(r) and False)
        if _jobs.empty():
            _trim()
