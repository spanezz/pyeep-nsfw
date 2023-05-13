from __future__ import annotations

import statistics
import time
from collections import deque
from typing import NamedTuple

import numpy

from pyeep.app import Message, check_hub
from pyeep.gtk import Gtk, GLib

from ..joystick import JoystickAxisMoved
from .base import SingleGroupPowerScene, register


class Sample(NamedTuple):
    time: float
    value: float


class Axis:
    def __init__(self, window_width: float = 3.0):
        self.values: deque[Sample] = deque()
        # Window width in seconds
        self.window_width: float = window_width

    def add(self, value: float):
        cur_time = time.time()
        self.values.append(Sample(cur_time, value))

        threshold = cur_time - self.window_width
        while self.values and self.values[0].time < threshold:
            self.values.popleft()

    def movement(self) -> float:
        if len(self.values) < 2:
            return 0.0
        mean = statistics.mean((x.value for x in self.values))
        delta = abs(self.values[-1].value - mean)
        return delta

    def tick(self):
        if not self.values:
            pass
        else:
            self.add(self.values[-1].value)


@register
class JSBondage(SingleGroupPowerScene):
    TITLE = "Joystick bondage"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.axes: dict[int, Axis] = {}
        self.timeout: int | None = None

    @check_hub
    def set_active(self, value: bool):
        if value:
            self.timeout = GLib.timeout_add(100, self.on_tick)
        else:
            if self.timeout is not None:
                GLib.source_remove(self.timeout)
                self.timeout = None
        super().set_active(value)

    @check_hub
    def update_timer(self):
        if self.timeout is not None:
            GLib.source_remove(self.timeout)
            self.timeout = None

    @check_hub
    def on_tick(self):
        for a in self.axes.values():
            a.tick()
        self._check_variance()
        return True

    def build(self) -> Gtk.Expander:
        expander = super().build()
        grid = expander.get_child()
        row = grid.max_row

        reset = Gtk.Button.new_with_label("Reset")
        reset.connect("clicked", self.reset)
        grid.attach(reset, 0, row, height=1)

        return expander

    @check_hub
    def reset(self, button):
        for axis in self.axes.values():
            axis.values.clear()
        self.set_power(0)

    def _check_variance(self):
        if self.axes:
            movement = max(a.movement() for a in self.axes.values())
        else:
            movement = 0.0

        # threshold = 0.0015
        # cap = 0.005
        threshold = 0.01
        cap = 0.6
        if movement > threshold:
            power = numpy.clip((movement - threshold) / cap, 0, 1)
            print(f"EEK! {movement:.5f} {power}")
            self.set_power(power)
        else:
            print(f"OK {movement:.5f}")
            self.set_power(0)

        # if msg.axis not in self.reference_values:
        #     self.reference_values[msg.axis] = msg.value

        # max_delta = 0.0
        # for axis, ref_val in self.reference_values.items():
        #     val = self.last_values[axis]
        #     if (delta := abs(val - ref_val)) > max_delta:
        #         max_delta = delta

        # if max_delta > 0.02:
        #     power = numpy.clip(max_delta, 0, 1)
        #     print("EEK!", max_delta, power)
        #     self.send(output.SetActivePower(power=max_delta * 100))
        # else:
        #     self.send(output.SetActivePower(power=0))

    @check_hub
    def receive(self, msg: Message):
        if not self.is_active:
            return

        match msg:
            case JoystickAxisMoved():
                if (axis := self.axes.get(msg.axis)) is None:
                    axis = Axis()
                    self.axes[msg.axis] = axis

                axis.add(msg.value)
                self._check_variance()
