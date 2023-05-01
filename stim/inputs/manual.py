from __future__ import annotations

from typing import Type

from pyeep.app import Message, check_hub
from pyeep.gtk import Gtk, GtkComponent
from pyeep.inputs import Input, InputController, InputSetActive, InputSetMode

from ..keyboards import Shortcut


class Manual(Input, GtkComponent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.active = True

    def build(self) -> None:
        return None

    @property
    def description(self) -> str:
        return "Manual"

    def get_input_controller(self) -> Type["InputController"]:
        return ManualInputController

    @check_hub
    def mode_default(self, value: str):
        if self.is_active:
            self.send(Shortcut(command=value))

    @check_hub
    def receive(self, msg: Message):
        match msg:
            case InputSetActive():
                if msg.input == self:
                    self.active = msg.value
            case InputSetMode():
                if msg.input == self:
                    self.mode = getattr(self, "mode_" + msg.mode)


class ManualInputController(InputController):
    def build(self) -> Gtk.Box:
        grid = super().build()
        pulse = Gtk.Button(label="Pulse")
        pulse.connect("clicked", self.on_pulse)
        grid.attach(pulse, 0, 3, 1, 1)
        return grid

    def on_pulse(self, button):
        self.input.mode("PULSE")
