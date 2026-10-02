import math
from typing import cast, Protocol

from fabric import Property, Service, Signal
from gi.repository import GLib, Gtk


class AnimatorFunction(Protocol):
    def do_function_step(self, t: float): ...


class BezierAnimator:
    def __init__(
        self,
        bezier_curve: tuple[float, float, float, float],
    ):
        self.bezier_curve = bezier_curve

    def do_function_step(self, time: float):
        y_points = (
            0,
            self.bezier_curve[1],
            self.bezier_curve[3],
            0,
        )
        return (
            (1 - time) ** 3 * y_points[0]
            + 3 * (1 - time) ** 2 * time * y_points[1]
            + 3 * (1 - time) * time**2 * y_points[2]
            + time**3 * y_points[3]
        )


class EaseOutBounce:
    def do_function_step(self, t: float):
        if t < 4 / 11:
            return 121 * t * t / 16
        elif t < 8 / 11:
            return (363 / 40.0 * t * t) - (99 / 10.0 * t) + 17 / 5.0
        elif t < 9 / 10:
            return (4356 / 361.0 * t * t) - (35442 / 1805.0 * t) + 16061 / 1805.0
        return (54 / 5.0 * t * t) - (513 / 25.0 * t) + 268 / 25.0


class EaseOutElastic:
    def do_function_step(self, t: float):
        c4 = (2 * math.pi) / 3
        return math.sin((t * 10 - 0.75) * c4) * math.pow(2, -10 * t) + 1


class Animator(Service):
    @Signal
    def finished(self) -> None: ...

    @Property(float, "read-write")
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, value: float):
        self._value = value
        return

    @Property(float, "read-write")
    def max_value(self) -> float:
        return self._max_value

    @max_value.setter
    def max_value(self, value: float):
        self._max_value = value
        return

    @Property(float, "read-write")
    def min_value(self) -> float:
        return self._min_value

    @min_value.setter
    def min_value(self, value: float):
        self._min_value = value
        return

    @Property(bool, "read-write", default_value=False)
    def playing(self) -> bool:
        return self._playing

    @playing.setter
    def playing(self, value: bool):
        self._playing = value
        return

    @Property(bool, "read-write", default_value=False)
    def repeat(self) -> bool:
        return self._repeat

    @repeat.setter
    def repeat(self, value: bool):
        self._repeat = value
        return

    def __init__(
        self,
        animator_function: AnimatorFunction,
        duration: float,
        min_value: float = 0.0,
        max_value: float = 1.0,
        repeat: bool = False,
        tick_widget: Gtk.Widget | None = None,
        custom_curve: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._duration = 5
        self._value = 0.0
        self._min_value = 0.0
        self._max_value = 1.0
        self._repeat = False

        self.animator_function = animator_function
        self.duration = duration
        self.value = min_value
        self.min_value = min_value
        self.max_value = max_value
        self.repeat = repeat

        self.playing = False
        self._start_time = None
        self._tick_handler = None
        self._timeline_pos = 0
        self._tick_widget = tick_widget

    def do_get_time_now(self):
        return GLib.get_monotonic_time() / 1_000_000

    def do_lerp(self, start: float, end: float, time: float) -> float:
        return start + (end - start) * time

    def do_update_value(self, delta_time: float):
        if not self.playing:
            return

        elapsed_time = delta_time - cast(float, self._start_time)

        self._timeline_pos = min(1, elapsed_time / self.duration)

        self.value = self.do_lerp(
            self.min_value,
            self.max_value,
            self.animator_function.do_function_step(self._timeline_pos),
        )

        if not self._timeline_pos >= 1:
            return

        if not self.repeat:
            self.value = self.max_value
            self.finished()
            self.pause()
            return

        self._start_time = delta_time
        self._timeline_pos = 0
        return

    def do_handle_tick(self, *_):
        current_time = self.do_get_time_now()
        self.do_update_value(current_time)
        return True

    def do_remove_tick_handlers(self):
        if self._tick_handler:
            if self._tick_widget:
                self._tick_widget.remove_tick_callback(self._tick_handler)
            else:
                GLib.source_remove(self._tick_handler)
        self._tick_handler = None
        return

    def play(self):
        if self.playing:
            return

        self._start_time = self.do_get_time_now()

        if not self._tick_handler:
            if self._tick_widget:
                self._tick_handler = self._tick_widget.add_tick_callback(
                    self.do_handle_tick
                )
            else:
                self._tick_handler = GLib.timeout_add(16, self.do_handle_tick)

        self.playing = True
        return

    def pause(self):
        self.playing = False
        return self.do_remove_tick_handlers()

    def stop(self):
        if not self._tick_handler:
            self._timeline_pos = 0
            self.playing = False
            return
        return self.do_remove_tick_handlers()
