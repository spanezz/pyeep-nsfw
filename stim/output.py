from __future__ import annotations

import logging
from typing import Type

import pyeep.aio
from pyeep.app import Message, Shutdown, check_hub
from pyeep.gtk import Gio, GLib, Gtk
from pyeep.animation import PowerAnimation, ColorAnimation, PowerAnimator, ColorAnimator
import pyeep.outputs.base
from pyeep.outputs.base import Output

from pyeep.messages import EmergencyStop
from .messages import Decrement, Increment, Pause, Resume
from pyeep.types import Color

log = logging.getLogger(__name__)


class SetPower(Message):
    def __init__(self, *, output: "Output", power: float, **kwargs):
        super().__init__(**kwargs)
        self.output = output
        self.power = power

    def __str__(self) -> str:
        return super().__str__() + f"(output={self.output}, power={self.power})"


class SetColor(Message):
    def __init__(self, *, output: "Output", color: Color, **kwargs):
        super().__init__(**kwargs)
        self.output = output
        self.color = color

    def __str__(self) -> str:
        return (
            super().__str__() +
            f"(output={self.output.description},"
            f" red={self.color[0]:.3f}, green={self.color[1]:.3f}, blue={self.color[2]:.3f})"
        )


class SetGroupPower(Message):
    """
    Set the power of the active output
    """
    def __init__(self, *, group: int, power: float | PowerAnimation, **kwargs):
        super().__init__(**kwargs)
        self.group = group
        self.power = power

    def __str__(self) -> str:
        return super().__str__() + f"(group={self.group}, power={self.power})"


class SetGroupColor(Message):
    """
    Set the power of the active output
    """
    def __init__(self, *, group: int, color: Color | ColorAnimation, **kwargs):
        super().__init__(**kwargs)
        self.group = group
        self.color = color

    def __str__(self) -> str:
        return super().__str__() + f"(group={self.group}, color={self.color}"


class IncreaseGroupPower(Message):
    """
    Increase the power of the active output by a given amount
    """
    def __init__(self, *, group: int, amount: float | PowerAnimation, **kwargs):
        super().__init__(**kwargs)
        self.group = group
        self.amount = amount

    def __str__(self) -> str:
        return super().__str__() + f"(group={self.group}, amount={self.amount})"


class NullOutput(Output, pyeep.aio.AIOComponent):
    """
    Output that does nothing besides tracking the last set power value
    """
    def __init__(self, **kwargs):
        kwargs.setdefault("rate", 20)
        super().__init__(**kwargs)
        self.power: float = 0.0

    @property
    def description(self) -> str:
        return "Null output"

    def get_output_controller(self) -> Type["OutputController"]:
        return ColoredOutputController

    async def run(self):
        while True:
            msg = await self.next_message()
            match msg:
                case Shutdown():
                    break
                case SetPower():
                    if msg.output == self:
                        self.power = msg.power


class OutputController(pyeep.outputs.base.OutputController):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.active = Gio.SimpleAction.new_stateful(
                name=self.name.replace("_", "-") + "-active",
                parameter_type=None,
                state=GLib.Variant.new_boolean(False))
        # self.active.connect("activate", self.on_activate)
        self.hub.app.gtk_app.add_action(self.active)

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

        self.pause = Gio.SimpleAction.new_stateful(
                name=self.name.replace("_", "-") + "-pause",
                parameter_type=None,
                state=GLib.Variant.new_boolean(False))
        self.pause.connect("change-state", self.on_pause)
        self.hub.app.gtk_app.add_action(self.pause)

        self.manual = Gio.SimpleAction.new_stateful(
                name=self.name.replace("_", "-") + "-manual",
                parameter_type=None,
                state=GLib.Variant.new_boolean(False))
        self.manual.connect("change-state", self.on_manual)
        self.hub.app.gtk_app.add_action(self.manual)

        self.power_animator = PowerAnimator(self.name, self.output.rate, self.set_animated_power)

    # UI handlers

    @check_hub
    def on_power(self, adj):
        """
        When the Adjustment value is changed, message the output with the new
        power level
        """
        val = round(adj.get_value())
        if not self._is_paused:
            self.send(SetPower(output=self.output, power=val / 100.0))

    @check_hub
    def on_power_min(self, adj):
        val = round(adj.get_value())
        self.power.set_lower(val)
        if (power := round(self.power.get_value())) < val:
            self.power.set_value(power)

    @check_hub
    def on_power_max(self, adj):
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

    @check_hub
    def on_manual(self, action, parameter):
        """
        When the manual mode is disabled, leave the previous value
        """
        new_state = not self.manual.get_state().get_boolean()
        self.manual.set_state(GLib.Variant.new_boolean(new_state))
        if new_state:
            self.set_manual_power(int(round(self.power.get_value())))
        else:
            self.exit_manual_mode()

    @check_hub
    def on_pause(self, action, parameter):
        """
        When the pause mode is disabled, restore the previous value
        """
        new_state = not self.pause.get_state().get_boolean()
        self.set_paused(new_state)

    # High-level actions

    @property
    def _is_paused(self) -> bool:
        return self.pause.get_state().get_boolean()

    @property
    def _is_manual(self) -> bool:
        return self.manual.get_state().get_boolean()

    @check_hub
    def set_power(self, power: int):
        """
        Set power to use when not in manual mode and not paused
        """
        if not self._is_manual:
            self.power.set_value(power)

    @check_hub
    def set_animated_power(self, power: float):
        """
        Add to the current power the power generated by the animator
        """
        if not self._is_manual and not self._is_paused:
            value = self.power.get_value() / 100.0
            value += power
            if value > 1:
                value = 1
            self.send(SetPower(output=self.output, power=value))

    @check_hub
    def adjust_power(self, delta: int):
        """
        Add the given amount to the current power value
        """
        if not self._is_manual:
            self.set_power(
                self.power.get_value() + delta)

    @check_hub
    def set_manual_power(self, power: int):
        """
        Set manual mode and maunal mode power
        """
        if not self._is_manual:
            self.manual.set_state(GLib.Variant.new_boolean(True))
        self.power.set_value(power)

    @check_hub
    def exit_manual_mode(self):
        """
        Exit manual mode
        """
        self.manual.set_state(GLib.Variant.new_boolean(False))

    @check_hub
    def set_paused(self, paused: bool):
        """
        Enter/exit pause mode
        """
        if self._is_paused != paused:
            self.pause.set_state(GLib.Variant.new_boolean(paused))
            if paused:
                self.send(SetPower(output=self.output, power=0))
            else:
                power = self.power.get_value() / 100.0
                self.send(SetPower(output=self.output, power=power))

    def build(self) -> Gtk.Grid:
        grid = super().build()

        pause = Gtk.ToggleButton(label="Paused")
        pause.set_action_name("app." + self.pause.get_name())
        grid.attach(pause, 1, 1, 1, 1)

        manual = Gtk.ToggleButton(label="Manual")
        manual.set_action_name("app." + self.manual.get_name())
        grid.attach(manual, 2, 1, 1, 1)

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

    @property
    @check_hub
    def is_active(self) -> bool:
        return self.active.get_state().get_boolean()

    @check_hub
    def receive(self, msg: Message):
        match msg:
            case EmergencyStop():
                self.set_power(0)
                self.set_paused(True)
            case Pause():
                if self.group.get_value() == msg.group:
                    self.set_paused(True)
            case Resume():
                if self.group.get_value() == msg.group:
                    self.set_paused(False)
            case Increment():
                if self.group.get_value() == msg.group:
                    self.adjust_power(2)
            case Decrement():
                if self.group.get_value() == msg.group:
                    self.adjust_power(-2)
            case SetGroupPower():
                if self.group.get_value() == msg.group:
                    self.set_power(round(msg.power * 100.0))
            case IncreaseGroupPower():
                if self.group.get_value() == msg.group:
                    match msg.amount:
                        case float():
                            self.adjust_power(msg.amount)
                        case PowerAnimation():
                            self.power_animator.start(msg.amount)


class ColoredOutputController(OutputController):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.color = Gtk.ColorButton()
        self.color.connect("color-activated", self.on_color)
        self.color_animator = ColorAnimator(self.name, self.output.rate, self.set_animated_color)

    @check_hub
    def receive(self, msg: Message):
        match msg:
            case SetGroupColor():
                if self.group.get_value() == msg.group:
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
        self.send(SetColor(
            output=self.output,
            color=(rgba.red, rgba.green, rgba.blue)))

    def set_color(self, color: Color):
        self.stop_animation()
        self.color.set_rgba(color.as_rgba())
        self.send(SetColor(output=self.output, color=color))

    def set_animated_color(self, color: Color):
        self.color.set_rgba(color.as_rgba())
        self.send(SetColor(output=self.output, color=color))

    def build(self) -> Gtk.Grid:
        grid = super().build()
        grid.attach(self.color, 3, 1, 1, 1)
        return grid
