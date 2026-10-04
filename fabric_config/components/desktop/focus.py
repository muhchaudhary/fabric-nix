"""A focus (pomodoro) timer, started by clicking the desktop clock."""

import time

from fabric.core.service import Service, Signal
from gi.repository import GLib

from fabric_config.utils.process import run_command_async

DEFAULT_MINUTES = 25


class FocusTimer(Service):
    @Signal
    def changed(self) -> None: ...

    @Signal
    def started(self, minutes: int) -> None: ...

    @Signal
    def finished(self, minutes: int) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._ends_at: float | None = None
        self._minutes = DEFAULT_MINUTES
        self._tick_id: int | None = None

    @property
    def running(self) -> bool:
        return self._ends_at is not None

    @property
    def remaining(self) -> int:
        """Whole seconds left, or 0 when not running."""
        if self._ends_at is None:
            return 0
        return max(0, round(self._ends_at - time.monotonic()))

    @property
    def ends_at_clock(self) -> float | None:
        """Wall-clock time the timer ends, for display."""
        if self._ends_at is None:
            return None
        return time.time() + (self._ends_at - time.monotonic())

    def start(self, minutes: int = DEFAULT_MINUTES):
        self.cancel(notify=False)
        self._minutes = minutes
        self._ends_at = time.monotonic() + minutes * 60
        self._tick_id = GLib.timeout_add_seconds(1, self._tick)
        self.changed()
        self.started(minutes)

    def cancel(self, notify: bool = True):
        if self._tick_id is not None:
            GLib.source_remove(self._tick_id)
            self._tick_id = None
        was_running = self._ends_at is not None
        self._ends_at = None
        if notify and was_running:
            self.changed()

    def toggle(self):
        if self.running:
            self.cancel()
        else:
            self.start(self._minutes)

    def _tick(self):
        if self.remaining > 0:
            self.changed()
            return True
        self._tick_id = None
        self._ends_at = None
        self.changed()
        self.finished(self._minutes)
        run_command_async(
            [
                "notify-send",
                "--app-name=Focus",
                "--icon=alarm-symbolic",
                "Focus session done",
                f"{self._minutes} minutes are up. Time for a break.",
            ]
        )
        return False


_focus_timer: FocusTimer | None = None


def get_focus_timer() -> FocusTimer:
    """The one focus timer: the desktop clock runs it, the bar shows it."""
    global _focus_timer
    if _focus_timer is None:
        _focus_timer = FocusTimer()
    return _focus_timer
