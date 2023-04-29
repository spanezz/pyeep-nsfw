from __future__ import annotations

import logging

import pyeep.aio
from pyeep.app import Message, Shutdown, check_hub
from pyeep.gtk import Gio, GLib, Gtk, GtkComponent

from .messages import EmergencyStop

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
    def __init__(self, *, output: Output, **kwargs):  # active_action: Gio.Action
        kwargs.setdefault("name", "output_model_" + output.name)
        super().__init__(**kwargs)
        self.output = output

        # self.active_action = active_action
        # if not self.active_action.get_state().get_string():
        #     self.active_action.set_state(GLib.Variant.new_string(self.name))
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

        self.last_set_value: float = 0.0

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
        if not self._is_paused and not self._is_manual:
            self.power.set_value(power)
        self.last_set_value = power

    @check_hub
    def adjust_power(self, delta: int):
        """
        Add the given amount to the current power value
        """
        if not self._is_paused and not self._is_manual:
            self.set_power(
                self.power.get_value() + delta)
        else:
            self.last_set_value += delta
            if self.last_set_value < self.power.get_lower():
                self.last_set_value = self.power.get_lower()
            if self.last_set_value > self.power.get_upper():
                self.last_set_value = self.power.get_upper()

    @check_hub
    def set_manual_power(self, power: int):
        """
        Set manual mode and maunal mode power
        """
        if not self._is_manual:
            self.manual.set_state(GLib.Variant.new_boolean(True))
        self.last_set_value = power

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
                self.power.set_value(0)
                self.send(SetPower(output=self.output, power=0))
            else:
                self.power.set_value(self.last_set_value)

    def build(self) -> Gtk.Grid:
        grid = Gtk.Grid()

        label_name = Gtk.Label(label=self.output.description)
        label_name.wrap = True
        label_name.set_halign(Gtk.Align.START)
        grid.attach(label_name, 0, 0, 3, 1)

        active = Gtk.CheckButton(label="Active")
        active.set_action_name("app." + self.active.get_name())
        # detailed_name = Gio.Action.print_detailed_name(
        #         "app." + self.active_action.get_name(),
        #         GLib.Variant.new_string(self.name))
        # active.set_detailed_action_name(detailed_name)
        # active.set_action_target_value(GLib.Variant.new_string(self.name))
        grid.attach(active, 0, 1, 1, 1)

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
        grid.attach(power, 0, 2, 3, 1)

        def disable_scale_on_pause(action, parameter):
            power.set_sensitive(
                    not self.pause.get_state().get_boolean())

        self.pause.connect("change-state", disable_scale_on_pause)

        power_min = Gtk.SpinButton()
        power_min.set_adjustment(self.power_min)
        grid.attach(power_min, 0, 3, 1, 1)

        grid.attach(Gtk.Label(label="to"), 1, 3, 1, 1)

        power_max = Gtk.SpinButton()
        power_max.set_adjustment(self.power_max)
        grid.attach(power_max, 2, 3, 1, 1)

        return grid

    @check_hub
    def is_active(self) -> bool:
        # current = self.active_action.get_state().get_string()
        # return current == self.name
        return self.active.get_state().get_boolean()

    def receive(self, msg: Message):
        match msg:
            case EmergencyStop():
                self.set_paused(True)
            case SetActivePower():
                self.set_power(msg.power)
            case IncreaseActivePower():
                self.adjust_power(msg.amount)


class OutputsModel(GtkComponent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.output_models: list[OutputModel] = []
        # self.active_action = Gio.SimpleAction.new_stateful(
        #     name="current-output",
        #     parameter_type=GLib.VariantType("s"),
        #     state=GLib.Variant.new_string(""))
        # self.hub.app.gtk_app.add_action(self.active_action)

    def build(self) -> Gtk.Frame:
        w = Gtk.Frame(label="Outputs")
        w.set_vexpand(True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        w.set_child(box)
        return w

    # def on_active(self, button):
    #     if button.get_active():
    #         self.send(SetActiveOutput(output=self.output))

    # @check_hub
    # def get_active_index(self) -> int:
    #     names = [m.name for m in self.output_models]
    #     current = self.active_action.get_state().get_string()
    #     try:
    #         return names.index(current)
    #     except ValueError:
    #         self.logger.warning("%s: current output %r not in %r", current, names)
    #         return 0

    # @check_hub
    # def activate_next(self):
    #     current = self.get_active_index()
    #     current = (current + 1) % len(self.output_models)
    #     self.active_action.set_state(GLib.Variant.new_string(self.output_models[current].name))

    # @check_hub
    # def activate_prev(self):
    #     current = self.get_active_index()
    #     current = (current - 1) % len(self.output_models)
    #     self.active_action.set_state(GLib.Variant.new_string(self.output_models[current].name))

    @check_hub
    def receive(self, msg: Message):
        match msg:
            case NewOutput():
                output_model = self.hub.app.add_component(
                        OutputModel, output=msg.output)  # active_action=self.active_action)
                self.output_models.append(output_model)
                self.widget.get_child().append(output_model.widget)
            # case keyboards.CncCommand():
            #     match msg.command:
            #         case "+A":
            #             self.activate_next()
            #         case "-A":
            #             self.activate_prev()
