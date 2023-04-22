from __future__ import annotations

import logging

import pyeep.aio
from pyeep.app import Message, Shutdown, check_hub
from pyeep.gtk import Gio, GLib, Gtk, GtkComponent

log = logging.getLogger(__name__)


class NewOutput(Message):
    def __init__(self, *, output: "Output", **kwargs):
        super().__init__(**kwargs)
        self.output = output

    def __str__(self):
        return super().__str__() + f"({self.output.description})"


class SetPower(Message):
    def __init__(self, *, output: "Output", power: float, **kwargs):
        super().__init__(**kwargs)
        self.output = output
        self.power = power

    def __str__(self) -> str:
        return super().__str__() + f"(power={self.power})"


# class SetActiveOutput(Message):
#     def __init__(self, *, output: "Output", **kwargs):
#         super().__init__(**kwargs)
#         self.output = output
#
#     def __str__(self) -> str:
#         return super().__str__() + f"(output={self.output.description})"


class SetActivePower(Message):
    """
    Set the power of the active output
    """
    def __init__(self, *, power: float, **kwargs):
        super().__init__(**kwargs)
        self.power = power

    def __str__(self) -> str:
        return super().__str__() + f"(power={self.power})"


class IncreaseActivePower(Message):
    """
    Increase the power of the active output by a given amount
    """
    def __init__(self, *, amount: float, **kwargs):
        super().__init__(**kwargs)
        self.amount = amount

    def __str__(self) -> str:
        return super().__str__() + f"(amount={self.amount})"


class Output(pyeep.app.Component):
    """
    Generic base for output components
    """
    def __init__(self, *, rate: int, **kwargs):
        super().__init__(**kwargs)

        # Rate (changes per second) at which this output can take commands
        self.rate = rate

    @property
    def description(self) -> str:
        return self.name


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

    async def run(self):
        while True:
            msg = await self.next_message()
            match msg:
                case Shutdown():
                    break
                case SetPower():
                    if msg.output == self:
                        self.power = msg.power


class OutputModel(GtkComponent):
    def __init__(self, *, output: Output, active_action: Gio.Action, **kwargs):
        kwargs.setdefault("name", "output_model_" + output.name)
        super().__init__(**kwargs)
        self.output = output

        self.active_action = active_action
        if not self.active_action.get_state().get_string():
            self.active_action.set_state(GLib.Variant.new_string(self.name))

        self.power = Gtk.Adjustment(
                value=0,
                lower=0,
                upper=100,
                step_increment=5,
                page_increment=10,
                page_size=0)
        self.power.connect("value_changed", self.on_power)

        self.last_value: float = 0.0
        self.value_override: float | None = None

    def on_power(self, adj):
        val = round(adj.get_value())
        self.send(SetPower(output=self.output, power=val / 100.0))

    def build(self) -> Gtk.Box:
        w = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        w.set_hexpand(True)

        label_name = Gtk.Label(label=self.output.description)
        label_name.wrap = True
        label_name.set_halign(Gtk.Align.START)
        w.append(label_name)

        active = Gtk.CheckButton(label="Active")
        detailed_name = Gio.Action.print_detailed_name(
                "app." + self.active_action.get_name(),
                GLib.Variant.new_string(self.name))
        active.set_detailed_action_name(detailed_name)
        active.set_action_target_value(GLib.Variant.new_string(self.name))
        w.append(active)

        power = Gtk.Scale(
                orientation=Gtk.Orientation.HORIZONTAL,
                adjustment=self.power)
        power.set_digits(2)
        power.set_draw_value(False)
        for mark in (25, 50, 75):
            power.add_mark(
                value=mark,
                position=Gtk.PositionType.BOTTOM,
                markup=None
            )
        w.append(power)

        return w

    @check_hub
    def is_active(self) -> bool:
        current = self.active_action.get_state().get_string()
        return current == self.name

    @check_hub
    def set_value(self, value: float):
        if self.value_override is not None:
            self.power.set_value(self.value_override)
        else:
            self.power.set_value(value)
        self.last_value = value

    @check_hub
    def add_value(self, value: float):
        self.set_value(
            self.power.get_value() + value)

    def receive(self, msg: Message):
        match msg:
            # case cnc.CncCommand():
            #     match msg.command:
            #         case "EMERGENCY":
            #             self.value_override = None
            #             self.set_value(0)
            #         case "STOP":
            #             if self.is_active():
            #                 self.set_value(0)
            #         case "SPEED UP":
            #             if self.is_active():
            #                 self.add_value(
            #                     self.adjustment.get_minimum_increment())
            #         case "SLOW DOWN":
            #             if self.is_active():
            #                 self.add_value(
            #                     -self.adjustment.get_minimum_increment())
            #         case "+Z":
            #             if self.is_active():
            #                 self.value_override = 100
            #                 self.set_value(self.last_value)
            #         case "-Z":
            #             if self.is_active():
            #                 self.value_override = None
            #                 self.set_value(self.last_value)
            #         case "F+":
            #             if self.is_active():
            #                 self.add_value(1)
            #         case "F-":
            #             if self.is_active():
            #                 self.add_value(-1)
            case SetActivePower():
                if self.is_active():
                    self.set_value(msg.power)
            case IncreaseActivePower():
                if self.is_active():
                    self.add_value(msg.amount)


class OutputsModel(GtkComponent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.active_action = Gio.SimpleAction.new_stateful(
            name="current-output",
            parameter_type=GLib.VariantType("s"),
            state=GLib.Variant.new_string(""))
        self.hub.app.gtk_app.add_action(self.active_action)

    def build(self) -> Gtk.Frame:
        w = Gtk.Frame(label="Outputs")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        w.set_child(box)
        return w

    # def on_active(self, button):
    #     if button.get_active():
    #         self.send(SetActiveOutput(output=self.output))

    # def get_active_index(self) -> int:
    #     for idx, tv in enumerate(self.toy_views):
    #         if tv.is_active():
    #             return idx
    #     return 0

    def receive(self, msg: Message):
        match msg:
            case NewOutput():
                output = self.hub.app.add_component(OutputModel, output=msg.output, active_action=self.active_action)
                self.widget.get_child().append(output.widget)
            # case cnc.CncCommand():
            #     match msg.command:
            #         case "+A":
            #             new_active = self.get_active_index() + 1
            #             if new_active >= len(self.toy_views):
            #                 new_active = 0
            #             self.toy_views[new_active].active.set_active(True)
            #         case "-A":
            #             new_active = self.get_active_index() - 1
            #             if new_active < 0:
            #                 new_active = len(self.toy_views) - 1
            #             self.toy_views[new_active].active.set_active(True)
