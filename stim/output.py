from __future__ import annotations

import logging

from pyeep.app import Message, Shutdown, check_hub
import pyeep.aio
from pyeep.gtk import Gtk, GtkComponentBox, GtkComponentFrame

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


class SetActiveOutput(Message):
    def __init__(self, *, output: "Output", **kwargs):
        super().__init__(**kwargs)
        self.output = output

    def __str__(self) -> str:
        return super().__str__() + f"(output={self.output.description})"


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


class OutputView(GtkComponentBox):
    def __init__(self, *, output: Output, previous: OutputView | None = None, **kwargs):
        kwargs.setdefault("name", "tv_" + output.name)
        super().__init__(**kwargs)

        self.output = output

        self.set_hexpand(True)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.box.set_hexpand(True)
        self.append(self.box)

        self.label_name = Gtk.Label(label=output.description)
        self.label_name.wrap = True
        self.box.append(self.label_name)

        self.active = Gtk.CheckButton(label="Active")
        self.active.connect("toggled", self.on_active)
        self.box.append(self.active)
        if previous:
            self.active.set_group(previous.active)
        else:
            self.active.set_active(True)

        self.power = Gtk.Scale.new_with_range(
                orientation=Gtk.Orientation.HORIZONTAL,
                min=0,
                max=100,
                step=5)
        self.power.set_digits(2)
        self.power.set_draw_value(False)
        for mark in (25, 50, 75):
            self.power.add_mark(
                value=mark,
                position=Gtk.PositionType.BOTTOM,
                markup=None
            )
        self.box.append(self.power)
        self.adjustment = self.power.get_adjustment()

        self.power.connect("value_changed", self.on_power)
        self.last_value: float = 0.0
        self.value_override: float | None = None

    def on_active(self, button):
        if button.get_active():
            self.send(SetActiveOutput(output=self.output))

    def on_power(self, adj):
        val = round(adj.get_value())
        self.send(SetPower(output=self.output, power=val / 100.0))

    @check_hub
    def is_active(self) -> bool:
        return self.active.get_active()

    def set_value(self, value: float):
        if self.value_override is not None:
            self.adjustment.set_value(self.value_override)
        else:
            self.adjustment.set_value(value)
        self.last_value = value

    def add_value(self, value: float):
        self.set_value(
            self.adjustment.get_value() + value)

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


class OutputsView(GtkComponentFrame):
    def __init__(self, **kwargs):
        kwargs.setdefault("label", "Outputs")
        super().__init__(**kwargs)
        self.output_views: list[OutputView] = []
        # self.active: ToyView | None = None
        # self.set_hexpand(True)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(self.box)

        # self.scan = Gtk.ToggleButton.new_with_label("Device scan")
        # self.scan.connect("toggled", self.on_scan_toggled)
        # self.scan.set_vexpand(False)
        # self.append(self.scan)

        # self.toybox = Gtk.Box()
        # self.append(self.toybox)

    # def get_active_index(self) -> int:
    #     for idx, tv in enumerate(self.toy_views):
    #         if tv.is_active():
    #             return idx
    #     return 0

    # def on_scan_toggled(self, toggle):
    #     if self.scan.get_active():
    #         self.send(ScanRequest(dst="toys", scan=True))
    #     else:
    #         self.send(ScanRequest(dst="toys", scan=False))

    def receive(self, msg: Message):
        match msg:
            case NewOutput():
                previous = self.output_views[-1] if self.output_views else None
                tv = self.hub.app.add_component(OutputView, output=msg.output, previous=previous)
                # if not self.toy_views:
                #     tv.active.set_active(True)
                #     self.active = tv
                self.output_views.append(tv)
                self.box.append(tv)
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
