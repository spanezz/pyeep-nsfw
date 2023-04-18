from __future__ import annotations

import numpy

from pyeep.app import Message, check_hub
from pyeep.gtk import Gtk

from .. import output
from ..muse2 import HeadMoved
from .base import Scene, register


@register
class HeadPosition(Scene):
    TITLE = "Head position"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.reference_roll: float | None = None
        self.reference_pitch: float | None = None
        # TODO: replace with a Gtk backend for mode selection
        self.mode: str = "center_zero"

    def build(self):
        super().build()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(box)

        zero_center = Gtk.CheckButton(label="Zero on center")
        zero_center.connect("toggled", self.set_mode, "center_zero")
        zero_center.set_active(True)
        box.append(zero_center)

        mid_center_increase_up = Gtk.CheckButton(label="Middle on center, up increases")
        mid_center_increase_up.set_group(zero_center)
        mid_center_increase_up.connect("toggled", self.set_mode, "center_middle_increase_up")
        box.append(mid_center_increase_up)

        mid_center_increase_down = Gtk.CheckButton(label="Middle on center, down increases")
        mid_center_increase_down.set_group(zero_center)
        mid_center_increase_down.connect("toggled", self.set_mode, "center_middle_increase_down")
        box.append(mid_center_increase_down)

        max_center = Gtk.CheckButton(label="Max on center")
        max_center.set_group(zero_center)
        max_center.connect("toggled", self.set_mode, "center_max")
        box.append(max_center)

        self.control_angle = Gtk.Adjustment(
                value=60, upper=180, step_increment=5, page_increment=10)
        self.control_angle_button = Gtk.SpinButton()
        self.control_angle_button.set_adjustment(self.control_angle)
        box.append(self.control_angle_button)

        center = Gtk.Button.new_with_label("Recenter")
        center.connect("clicked", self.set_center)
        box.append(center)

    @check_hub
    def set_mode(self, button, mode: str):
        self.mode = mode

    @check_hub
    def set_center(self, button):
        self.reference_pitch = None
        self.reference_roll = None

    @check_hub
    def receive(self, msg: Message):
        match msg:
            case HeadMoved():
                if self.is_active():
                    if self.reference_roll is None:
                        self.reference_roll = msg.roll

                    if self.reference_pitch is None:
                        self.reference_pitch = msg.pitch

                    # roll_angle = self.reference_roll - roll
                    pitch_angle = self.reference_pitch - msg.pitch
                    control_angle = self.control_angle.get_value()
                    match self.mode:
                        case "center_zero":
                            power = numpy.clip(abs(pitch_angle) * 2 / control_angle, 0, 1)
                        case "center_middle_increase_up":
                            power = numpy.clip(0.5 - pitch_angle * 2 / control_angle, 0, 1)
                        case "center_middle_increase_down":
                            power = numpy.clip(0.5 + pitch_angle * 2 / control_angle, 0, 1)
                        case "center_max":
                            power = numpy.clip(1 - abs(pitch_angle) * 2 / control_angle, 0, 1)
                        case _:
                            self.logger.warning("Unknown mode %r", self.mode)
                            power = 0

                    self.send(output.SetActivePower(power=power * 100))
