from __future__ import annotations

from typing import Type

import pyeep.aio
from pyeep.app import Message
from pyeep.gtk import Gio, GLib, Gtk, GtkComponent


class InputSetActive(Message):
    def __init__(self, *, input: "Input", value: bool, **kwargs):
        super().__init__(**kwargs)
        self.input = input
        self.value = value

    def __str__(self) -> str:
        return super().__str__() + f"(input={self.input}, value={self.value})"


class Input(pyeep.app.Component):
    """
    Generic base for output components
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def description(self) -> str:
        return self.name

    def get_model(self) -> Type["InputModel"]:
        return InputModel

    def is_active(self) -> bool:
        raise NotImplementedError(f"{self.__class__.__name__}._is_active not implemented")


class InputModel(GtkComponent):
    def __init__(self, *, input: Input, **kwargs):
        kwargs.setdefault("name", "input_model_" + input.name)
        super().__init__(**kwargs)
        self.input = input

        self.active = Gio.SimpleAction.new_stateful(
                name=self.name.replace("_", "-"),
                parameter_type=None,
                state=GLib.Variant.new_boolean(self.input.active))
        self.active.connect("activate", self.on_activate)
        self.hub.app.gtk_app.add_action(self.active)

    def is_active(self) -> bool:
        return self.active.get_state().get_boolean()

    def on_activate(self, action, parameter):
        new_state = not self.active.get_state().get_boolean()
        self.active.set_state(GLib.Variant.new_boolean(new_state))
        self.send(InputSetActive(input=self.input, value=new_state))

    def build(self) -> Gtk.Box:
        grid = Gtk.Grid()

        label_name = Gtk.Label(label=self.input.description)
        label_name.wrap = True
        label_name.set_halign(Gtk.Align.START)
        grid.attach(label_name, 0, 0, 1, 1)

        active = Gtk.CheckButton(label="Active")
        active.set_action_name("app." + self.active.get_name())
        grid.attach(active, 0, 1, 1, 1)

        return grid
