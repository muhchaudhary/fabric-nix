"""Logging setup: one loguru sink for our logs, fabric's, GLib/GTK warnings and
uncaught exceptions, with repeated messages collapsed.

Call `setup_logging()` before anything else logs (top of `main.py`).

Environment:
- `FABRIC_LOG_LEVEL`: our level (default INFO; DEBUG, WARNING, ...)
- `FABRIC_LIB_LOG_LEVEL`: level for the fabric library itself (default
  WARNING: at INFO it reports every action registered and audio stream added)
"""

import os
import sys
import threading
import time

from gi.repository import GLib
from loguru import logger

# a message from one place may repeat this often per window before the rest
# are dropped and counted (a broken callback can fire thousands of times a
# second: one such loop once wrote ~285k identical tracebacks)
BURST = 5
WINDOW_S = 10.0

FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
)

_GLIB_LEVELS = {
    GLib.LogLevelFlags.LEVEL_ERROR: "CRITICAL",
    GLib.LogLevelFlags.LEVEL_CRITICAL: "ERROR",
    GLib.LogLevelFlags.LEVEL_WARNING: "WARNING",
    GLib.LogLevelFlags.LEVEL_MESSAGE: "INFO",
    GLib.LogLevelFlags.LEVEL_INFO: "INFO",
    GLib.LogLevelFlags.LEVEL_DEBUG: "DEBUG",
}
# domains whose g_warning/g_critical would otherwise go to stderr unformatted
_GLIB_DOMAINS = (
    None,
    "GLib",
    "GLib-GObject",
    "GLib-GIO",
    "Gtk",
    "Gdk",
    "GdkPixbuf",
    "Pango",
    "GtkLayerShell",
)


class _RateLimiter:
    """Drops a message's repeats past BURST per WINDOW_S, keyed by where it was
    logged (and the exception type), and notes how many were dropped on the
    next one let through."""

    def __init__(self):
        self._lock = threading.Lock()
        # key -> [window start, count in window, dropped since last shown]
        self._seen: dict[tuple, list] = {}

    def __call__(self, record) -> bool:
        exc = record["exception"]
        key = (record["name"], record["function"], record["line"])
        if exc:
            # uncaught ones all arrive through the excepthook: key them on
            # where they were raised
            tb = exc.traceback
            while tb is not None and tb.tb_next is not None:
                tb = tb.tb_next
            where = (tb.tb_frame.f_code.co_filename, tb.tb_lineno) if tb else None
            key += (exc.type, where)
        else:
            key += (record["message"],)
        now = time.monotonic()
        with self._lock:
            entry = self._seen.get(key)
            if entry is None or now - entry[0] >= WINDOW_S:
                dropped = entry[2] if entry else 0
                self._seen[key] = [now, 1, 0]
                if len(self._seen) > 2048:
                    self._prune(now)
            elif entry[1] < BURST:
                entry[1] += 1
                dropped = 0
            else:
                entry[2] += 1
                return False
        record["extra"]["repeats"] = (
            f" (repeated {dropped} more times)" if dropped else ""
        )
        return True

    def _prune(self, now: float):
        for key in [k for k, e in self._seen.items() if now - e[0] >= WINDOW_S]:
            if self._seen[key][2] == 0:
                del self._seen[key]


def _level(var: str, default: str) -> str:
    value = os.environ.get(var, default).upper()
    try:
        logger.level(value)
    except ValueError:
        return default
    return value


def _glib_handler(domain, level, message, _data):
    name = next(
        (n for flag, n in _GLIB_LEVELS.items() if level & flag),
        "WARNING",
    )
    logger.log(name, f"[{domain or 'GLib'}] {message}")


def _excepthook(exc_type, exc, tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    # PyGObject reports exceptions raised in signal handlers and GLib
    # callbacks through here too
    logger.opt(exception=(exc_type, exc, tb)).error("Uncaught exception")


def _thread_excepthook(args):
    if args.exc_type is SystemExit:
        return
    name = args.thread.name if args.thread else "?"
    logger.opt(exception=(args.exc_type, args.exc_value, args.exc_traceback)).error(
        f"Uncaught exception in thread {name}"
    )


def setup_logging():
    level = _level("FABRIC_LOG_LEVEL", "INFO")
    lib_level = _level("FABRIC_LIB_LOG_LEVEL", "WARNING")
    limiter = _RateLimiter()

    def keep(record) -> bool:
        name = record["name"] or ""
        minimum = level
        if name == "fabric" or name.startswith("fabric."):
            minimum = lib_level
        if record["level"].no < logger.level(minimum).no:
            return False
        return limiter(record)

    logger.remove()
    logger.add(
        sys.stderr,
        level=min(logger.level(level).no, logger.level(lib_level).no),
        # loguru appends the traceback, if any
        format=FORMAT + "<dim>{extra[repeats]}</dim>",
        filter=keep,
        backtrace=False,
        diagnose=False,
    )
    logger.configure(extra={"repeats": ""})

    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook
    flags = GLib.LogLevelFlags.LEVEL_MASK | GLib.LogLevelFlags.FLAG_FATAL
    for domain in _GLIB_DOMAINS:
        GLib.log_set_handler(domain, flags, _glib_handler, None)
