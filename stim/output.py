from __future__ import annotations

import logging
from typing import Type

import pyeep.aio
from pyeep.app import Message, Shutdown, check_hub
from pyeep.gtk import GLib, Gtk
from pyeep.animation import PowerAnimation, ColorAnimation, PowerAnimator, ColorAnimator
import pyeep.outputs.base
from pyeep.outputs.base import Output

from .messages import Decrement, Increment
from pyeep.types import Color

log = logging.getLogger(__name__)


class PowerOutput(Output):
    def set_power(self, power: float):
        raise NotImplementedError(f"{self.__class__.__name__}.set_power not implemented")


class ColorOutput(Output):
    def set_color(self, color: Color):
        raise NotImplementedError(f"{self.__class__.__name__}.set_color not implemented")


class SetGroupPower(Message):
    """
    Set the power of the outputs in the given group
    """
    def __init__(self, *, group: int, power: float | PowerAnimation, **kwargs):
        super().__init__(**kwargs)
        self.group = group
        self.power = power

    def __str__(self) -> str:
        return super().__str__() + f"(group={self.group}, power={self.power})"


class SetGroupColor(Message):
    """
    Set the power of the outputs in the given group
    """
    def __init__(self, *, group: int, color: Color | ColorAnimation, **kwargs):
        super().__init__(**kwargs)
        self.group = group
        self.color = color

    def __str__(self) -> str:
        return super().__str__() + f"(group={self.group}, color={self.color}"


class IncreaseGroupPower(Message):
    """
    Increase the power of an output group by a given amount
    """
    def __init__(self, *, group: int, amount: float | PowerAnimation, **kwargs):
        super().__init__(**kwargs)
        self.group = group
        self.amount = amount

    def __str__(self) -> str:
        return super().__str__() + f"(group={self.group}, amount={self.amount})"


class NullOutput(PowerOutput, ColorOutput, pyeep.aio.AIOComponent):
    """
    Output that does nothing besides tracking the last set power value
    """
    def __init__(self, **kwargs):
        kwargs.setdefault("rate", 20)
        super().__init__(**kwargs)
        self.power: float = 0.0
        self.color: Color = Color()

    @property
    def description(self) -> str:
        return "Null output"

    def get_output_controller(self) -> Type["pyeep.outputs.base.OutputController"]:
        class Controller(PowerOutputController, ColoredOutputController):
            pass
        return Controller

    @pyeep.aio.export
    def set_power(self, power: float):
        self.power = power

    @pyeep.aio.export
    def set_color(self, color: Color):
        self.color = color

    async def run(self):
        while True:
            msg = await self.next_message()
            match msg:
                case Shutdown():
                    break


class PowerOutputController(pyeep.outputs.base.OutputController):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.power = Gtk.Adjustment(
                value=0,
                lower=0,
                upper=100,
                step_increment=5,
                page_increment=10,
                page_size=0)
        self.power.connect("value_changed", self.on_power)

        self.power_min = Gtk.Adjustment(
                value=0,
                lower=0,
                upper=100,
                step_increment=5,
                page_increment=10,
                page_size=0)
        self.power_min.connect("value_changed", self.on_power_min)

        self.power_max = Gtk.Adjustment(
                value=100,
                lower=0,
                upper=100,
                step_increment=5,
                page_increment=10,
                page_size=0)
        self.power_max.connect("value_changed", self.on_power_max)

        self.power_animator = PowerAnimator(self.name, self.output.rate, self.set_animated_power)

    # Controller/UI handlers

    @check_hub
    def on_power(self, adj):
        """
        When the Adjustment value is changed, message the output with the new
        power level
        """
        val = round(adj.get_value())
        if not self.is_paused:
            self.output.set_power(val / 100.0)

    @check_hub
    def on_power_min(self, adj):
        """
        Adjust minimum power
        """
        val = round(adj.get_value())
        self.power.set_lower(val)
        if (power := round(self.power.get_value())) < val:
            self.power.set_value(power)

    @check_hub
    def on_power_max(self, adj):
        """
        Adjust maximum power
        """
        val = round(adj.get_value())
        self.power.set_upper(val)
        if (power := round(self.power.get_value())) > val:
            self.power.set_value(power)

    @check_hub
    def on_manual_power(self, scale, scroll, value):
        """
        When the Scale value is changed, activate manual mode
        """
        self.set_manual_power(int(round(value)))

    # High-level actions

    @check_hub
    def set_power(self, power: int):
        """
        Set power to use when not in manual mode and not paused
        """
        if not self.is_manual:
            self.power.set_value(power)

    @check_hub
    def set_animated_power(self, power: float):
        """
        Add to the current power the power generated by the animator
        """
        if not self.is_manual and not self.is_paused:
            value = self.power.get_value() / 100.0
            value += power
            if value > 1:
                value = 1
            self.output.set_power(value)

    @check_hub
    def adjust_power(self, delta: int):
        """
        Add the given amount to the current power value
        """
        if not self.is_manual:
            self.set_power(
                self.power.get_value() + delta)

    @check_hub
    def set_manual_power(self, power: int):
        """
        Set manual mode and maunal mode power
        """
        if not self.is_manual:
            self.manual.set_state(GLib.Variant.new_boolean(True))
        self.power.set_value(power)

    @check_hub
    def set_paused(self, paused: bool):
        """
        Enter/exit pause mode
        """
        super().set_paused(paused)

        if self.is_paused == paused:
            return

        if paused:
            self.output.set_power(0)
        else:
            power = self.power.get_value() / 100.0
            self.output.set_power(power)

    @check_hub
    def set_manual(self, manual: bool):
        """
        When the manual mode is disabled, leave the previous value
        """
        super().set_manual(manual)

        if self.is_manual == manual:
            return

        if manual:
            self.set_manual_power(int(round(self.power.get_value())))

    @check_hub
    def emergency_stop(self):
        self.set_power(0)
        super().emergency_stop()

    @check_hub
    def receive(self, msg: Message):
        match msg:
            case Increment():
                if self.in_group(msg.group):
                    self.adjust_power(2)
            case Decrement():
                if self.in_group(msg.group):
                    self.adjust_power(-2)
            case SetGroupPower():
                if self.in_group(msg.group):
                    self.set_power(round(msg.power * 100.0))
            case IncreaseGroupPower():
                if self.in_group(msg.group):
                    match msg.amount:
                        case float():
                            self.adjust_power(msg.amount)
                        case PowerAnimation():
                            self.power_animator.start(msg.amount)
            case _:
                super().receive(msg)

    def build(self) -> Gtk.Grid:
        grid = super().build()

        power = Gtk.Scale(
                orientation=Gtk.Orientation.HORIZONTAL,
                adjustment=self.power)
        power.set_digits(2)
        power.set_draw_value(False)
        power.set_hexpand(True)
        power.connect("change-value", self.on_manual_power)
        for mark in (25, 50, 75):
            power.add_mark(
                value=mark,
                position=Gtk.PositionType.BOTTOM,
                markup=None
            )
        grid.attach(power, 0, 2, 4, 1)

        power_min = Gtk.SpinButton()
        power_min.set_adjustment(self.power_min)
        grid.attach(power_min, 0, 4, 1, 1)

        grid.attach(Gtk.Label(label="to"), 1, 3, 1, 1)

        power_max = Gtk.SpinButton()
        power_max.set_adjustment(self.power_max)
        grid.attach(power_max, 2, 4, 1, 1)

        return grid


class ColoredOutputController(pyeep.outputs.base.OutputController):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.color = Gtk.ColorButton()
        self.color.connect("color-activated", self.on_color)
        self.color_animator = ColorAnimator(self.name, self.output.rate, self.set_animated_color)

    @check_hub
    def receive(self, msg: Message):
        match msg:
            case SetGroupColor():
                if self.in_group(msg.group):
                    match msg.color:
                        case Color():
                            self.set_color(msg.color)
                        case ColorAnimation():
                            self.color_animator.start(msg.color)
            case _:
                super().receive(msg)

    def stop_animation(self):
        self.color_animator.stop()

    def on_color(self, color):
        self.stop_animation()
        rgba = color.get_rgba()
        self.output.set_color(Color(rgba.red, rgba.green, rgba.blue))

    def set_color(self, color: Color):
        self.stop_animation()
        self.color.set_rgba(color.as_rgba())
        self.output.set_color(color)

    def set_animated_color(self, color: Color):
        self.color.set_rgba(color.as_rgba())
        self.output.set_color(color)

    def build(self) -> Gtk.Grid:
        grid = super().build()
        grid.attach(self.color, 3, 1, 1, 1)
        return grid
