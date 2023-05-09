from __future__ import annotations

import numpy

from pyeep.app import Message, check_hub
from pyeep.gtk import GLib, Gtk
from pyeep.types import Color

from .. import animation, output
from ..muse2 import HeadMoved, HeadShaken
from .base import SingleGroupScene, register


@register
class HeadPosition(SingleGroupScene):
    TITLE = "Head position"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.reference_roll: float | None = None
        self.reference_pitch: float | None = None

        self.control_angle = Gtk.Adjustment(
                value=60, upper=180, step_increment=5, page_increment=10)

        # TODO: replace with a Gtk backend for mode selection
        self.mode: str = "center_zero"

    def build(self) -> Gtk.Expander:
        expander = super().build()
        grid = expander.get_child()

        zero_center = Gtk.CheckButton(label="Zero on center")
        zero_center.connect("toggled", self.set_mode, "center_zero")
        zero_center.set_active(True)
        grid.attach(zero_center, 0, 1, 2, 1)

        mid_center_increase_up = Gtk.CheckButton(label="Middle on center, up increases")
        mid_center_increase_up.set_group(zero_center)
        mid_center_increase_up.connect("toggled", self.set_mode, "center_middle_increase_up")
        grid.attach(mid_center_increase_up, 0, 2, 2, 1)

        mid_center_increase_down = Gtk.CheckButton(label="Middle on center, down increases")
        mid_center_increase_down.set_group(zero_center)
        mid_center_increase_down.connect("toggled", self.set_mode, "center_middle_increase_down")
        grid.attach(mid_center_increase_down, 0, 3, 2, 1)

        max_center = Gtk.CheckButton(label="Max on center")
        max_center.set_group(zero_center)
        max_center.connect("toggled", self.set_mode, "center_max")
        grid.attach(max_center, 0, 4, 2, 1)

        control_angle_button = Gtk.SpinButton()
        control_angle_button.set_adjustment(self.control_angle)
        grid.attach(control_angle_button, 0, 5, 2, 1)

        center = Gtk.Button.new_with_label("Recenter")
        center.connect("clicked", self.set_center)
        grid.attach(center, 0, 6, 2, 1)

        return expander

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
                if self.is_active:
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

                    self.send(output.SetGroupPower(group=self.get_group(), power=power))


@register
class Consent(SingleGroupScene):
    TITLE = "Consent"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout: int | None = None

    @check_hub
    def start(self):
        super().start()
        self.timeout = GLib.timeout_add(500, self._tick)

    @check_hub
    def pause(self):
        if self.timeout is not None:
            GLib.source_remove(self.timeout)
            self.timeout = None
        super().pause()

    def _tick(self):
        # Slow decay
        self.send(output.IncreaseGroupPower(group=self.get_group(), amount=-0.005))
        return True

    @check_hub
    def receive(self, msg: Message):
        match msg:
            case HeadShaken():
                if self.is_active:
                    match msg.axis:
                        case "z":
                            # No
                            self.send(output.IncreaseGroupPower(group=self.get_group(), amount=-msg.freq / 500))
                        case "y":
                            # Yes
                            self.send(output.IncreaseGroupPower(group=self.get_group(), amount=msg.freq / 500))

                    # Normalized frequency and power
                    # freq: 0..5.5
                    # power: 50..72
                    freq = msg.freq / 5.5
                    if freq < 0:
                        freq = 0
                    elif freq > 1:
                        freq = 1

                    power = (msg.power - 50) / 22
                    if power < 0:
                        power = 0
                    elif power > 1:
                        power = 1

                    value = 0.1 + max(freq, power) * 0.9
                    match msg.axis:
                        case "x":
                            # Meh
                            color = Color(value/2, value/2, 0)
                            self.send(output.SetGroupColor(
                                group=self.get_group(),
                                color=animation.ColorPulse(color=color)))
                        case "z":
                            # No
                            color = Color(value, 0, 0)
                            # self.send(output.SetActiveColor(color=color))
                            self.send(output.SetGroupColor(
                                group=self.get_group(),
                                color=animation.ColorPulse(color=color)))
                        case "y":
                            # Yes
                            color = Color(0, value, 0)
                            # self.send(output.SetActiveColor(color=color)
                            self.send(output.SetGroupColor(
                                group=self.get_group(),
                                color=animation.ColorPulse(color=color)))
