from __future__ import annotations

import numpy

from pyeep.app import Message, check_hub
from pyeep.gtk import Gtk

from .. import output
from ..joystick import JoystickAxisMoved
from .base import Scene, register


@register
class JSBondage(Scene):
    TITLE = "Joystick bondage"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.reference_values: dict[int, float] = {}
        self.last_values: dict[int, float] = {}

    def build(self) -> Gtk.Expander:
        expander = super().build()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        expander.set_child(box)

        center = Gtk.Button.new_with_label("Recenter")
        center.connect("clicked", self.set_center)
        box.append(center)

        return expander

    @check_hub
    def set_center(self, button):
        self.reference_values = self.last_values.copy()
        self.send(output.SetActivePower(power=0))

    @check_hub
    def receive(self, msg: Message):
        match msg:
            case JoystickAxisMoved():
                if self.is_active():
                    self.last_values[msg.axis] = msg.value

                    if msg.axis not in self.reference_values:
                        self.reference_values[msg.axis] = msg.value

                    max_delta = 0.0
                    for axis, ref_val in self.reference_values.items():
                        val = self.last_values[axis]
                        if (delta := abs(val - ref_val)) > max_delta:
                            max_delta = delta

                    if max_delta > 0.02:
                        power = numpy.clip(max_delta, 0, 1)
                        print("EEK!", max_delta, power)
                        self.send(output.SetActivePower(power=max_delta * 100))
                    else:
                        self.send(output.SetActivePower(power=0))
