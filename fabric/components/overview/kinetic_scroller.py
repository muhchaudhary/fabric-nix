# Testing file for kinetic motion to scrolling

from fabric.widgets.eventbox import EventBox
from fabric.utils import clamp, invoke_repeater
from fabric.service import Signal, SignalContainer
import math
from loguru import logger


class KineticScroll(EventBox):
    __gsignals__ = SignalContainer(
        Signal("smooth-scroll-event", "run-first", None, (float,)),
        Signal("normal-scroll-event", "run-first", None, (float,)),
    )

    def __init__(self, multiplier: float, min_value: int, max_value: int, **kwargs):
        super().__init__(
            # TODO add normal scrolling later
            events="smooth-scroll",
            **kwargs,
        )
        self._mult = multiplier
        self._min = min_value
        self._max = max_value
        self.scroll_value = 0
        self.is_scrolling = False

        # Samples
        self.n_samples = 4
        self.samples = [0] * self.n_samples
        self.connect("scroll-event", self.on_scroll_event)

    # currently will only handle smooth scroll events
    def on_scroll_event(self, widget, event):
        self.is_scrolling = True
        val_y = event.delta_y
        if val_y != 0:
            adj_delta = val_y * self._mult
            self.scroll_value += adj_delta
            self.scroll_value = clamp(self.scroll_value, self._min, self._max)

            self.emit("smooth-scroll-event", self.scroll_value)

            # use a circular buffer type structure, this sucks
            self.samples.pop()
            self.samples.append(adj_delta)
        else:
            # invoke repeater to run the kinetic scroll simulation here
            self.ticks = 0
            logger.info(f"Velocity: {sum(self.samples) / self.n_samples}")
            self.is_scrolling = False
            invoke_repeater(
                8, self.on_scroll_event_end, sum(self.samples) / self.n_samples
            )

    # kinetic scroll simulation
    def on_scroll_event_end(self, velocity):
        if self.is_scrolling:
            return False

        new_velocity = self.easing_function(abs(velocity), self.ticks)

        if self.scroll_value + new_velocity >= self._max:
            self.scroll_value = self._max
            self.emit("smooth-scroll-event", self.scroll_value)
            return False

        if self.scroll_value - new_velocity <= self._min:
            self.scroll_value = self._min
            self.emit("smooth-scroll-event", self.scroll_value)
            return False
        print(new_velocity, self.scroll_value)
        self.scroll_value += new_velocity if velocity > 0 else -new_velocity
        self.ticks += 0.008
        self.emit("smooth-scroll-event", self.scroll_value)

        return True if abs(new_velocity) > 0.2 else False

    def easing_function(self, velocity, time):
        return velocity * math.exp(-2 * (1 / velocity) * time)
        # return -1/3 * time + velocity
