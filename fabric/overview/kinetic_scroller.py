# Testing file for kinetic motion to scrolling

from fabric.widgets.eventbox import EventBox
from fabric.utils import clamp, invoke_repeater
from fabric.service import *
import math

class KineticScroll(EventBox):
    __gsignals__ = SignalContainer(
        Signal("smooth-scroll-event", "run-first", None, (float,)),
        Signal("normal-scroll-event", "run-first", None, (float,))
    )
    def __init__(self, mult: float, min_value: int, max_value: int, **kwargs):
        super().__init__(
            # TODO add normal scrolling later
            events="smooth-scroll",
            **kwargs
        )
        self._mult = mult
        self._min = min_value
        self._max = max_value
        self.scroll_value = 0

        # Samples
        self.n_samples = 4
        self.samples = [0] * self.n_samples
        self.connect("scroll-event", self.on_scroll_event)

    #currently will only handle smooth scroll events
    def on_scroll_event(self, widget, event):
        val_y = event.delta_y
        if val_y != 0:
            adj_delta = val_y * self._mult
            self.scroll_value += adj_delta
            self.scroll_value = clamp(self.scroll_value, self._min, self._max)

            # TODO: create a new smooth-scroll-event signal
            self.emit("smooth-scroll-event", self.scroll_value)

            # use a circular buffer type structure, this sucks
            self.samples.pop()
            self.samples.append(adj_delta)
        else:
            # invoke repeater to run the kinetic scroll simulation here
            self.ticks = 0
            print("Velocity: ", sum(self.samples) / self.n_samples)
            invoke_repeater(1, self.on_scroll_event_end, sum(self.samples) / self.n_samples)

    # kinetic scroll simulation
    def on_scroll_event_end(self, velocity):
        new_velocity = self.easing_funct(abs(velocity),self.ticks)
        if self.scroll_value + new_velocity >= self._max:
            return False
        self.scroll_value += new_velocity if velocity > 0 else -new_velocity
        print(new_velocity)
        self.ticks += 0.001
        self.emit("smooth-scroll-event", self.scroll_value)
        return True if abs(new_velocity) > 0.001 else False

    def easing_funct(self, velocity, time):
        return velocity * math.exp(-2*(1/velocity) * time)