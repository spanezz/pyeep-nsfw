from __future__ import annotations

import inspect
from typing import Type

import pyeep.aio
from pyeep.app import Message
from pyeep.gtk import Gio, GLib, Gtk, GtkComponent


class InputSetActive(Message):
    """
    Activate/deactivate an input
    """
    def __init__(self, *, input: "Input", value: bool, **kwargs):
        super().__init__(**kwargs)
        self.input = input
        self.value = value

    def __str__(self) -> str:
        return super().__str__() + f"(input={self.input}, value={self.value})"


class InputSetMode(Message):
    """
    Set the mode for an input
    """
    def __init__(self, *, input: "Input", mode: str, **kwargs):
        super().__init__(**kwargs)
        self.input = input
        self.mode = mode

    def __str__(self) -> str:
        return super().__str__() + f"(input={self.input}, mode={self.mode})"


class Input(pyeep.app.Component):
    """
    Generic base for output components
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mode = self.mode_default

    @property
    def description(self) -> str:
        return self.name

    def get_model(self) -> Type["InputModel"]:
        return InputModel

    def is_active(self) -> bool:
        raise NotImplementedError(f"{self.__class__.__name__}._is_active not implemented")

    def mode_default(self):
        """
        Default input behaviour
        """
        pass


class InputModel(GtkComponent):
    def __init__(self, *, input: Input, **kwargs):
        kwargs.setdefault("name", "input_model_" + input.name)
        super().__init__(**kwargs)
        self.input = input

        # self.modes: dict[str, str] = {}

        self.active = Gio.SimpleAction.new_stateful(
                name=self.name.replace("_", "-") + "-active",
                parameter_type=None,
                state=GLib.Variant.new_boolean(self.input.active))
        self.active.connect("activate", self.on_activate)
        self.hub.app.gtk_app.add_action(self.active)

        self.modes = Gtk.ListStore(str, str)
        for name, value in inspect.getmembers(self.input, inspect.ismethod):
            if not name.startswith("mode_"):
                continue
            self.modes.append([name[5:], inspect.getdoc(value)])

        # self.mode = Gio.SimpleAction.new_stateful(
        #         name=self.name.replace("_", "-") + "-mode",
        #         parameter_type=GLib.VariantType("s"),
        #         state=GLib.Variant.new_string("default"))
        # self.hub.app.gtk_app.add_action(self.mode)

        # if not self.active_action.get_state().get_string():
        #     self.active_action.set_state(GLib.Variant.new_string(self.name))

        # current = self.active_action.get_state().get_string()
        # return current == self.name

        # detailed_name = Gio.Action.print_detailed_name(
        #         "app." + self.active_action.get_name(),
        #         GLib.Variant.new_string(self.name))
        # active.set_detailed_action_name(detailed_name)
        # active.set_action_target_value(GLib.Variant.new_string(self.name))

    def is_active(self) -> bool:
        return self.active.get_state().get_boolean()

    def on_activate(self, action, parameter):
        new_state = not self.active.get_state().get_boolean()
        self.active.set_state(GLib.Variant.new_boolean(new_state))
        self.send(InputSetActive(input=self.input, value=new_state))

    def on_mode_changed(self, combo):
        tree_iter = combo.get_active_iter()
        if tree_iter is not None:
            model = combo.get_model()
            mode = model[tree_iter][0]
            print("Selected: mode", mode)

    def build(self) -> Gtk.Box:
        grid = Gtk.Grid()

        label_name = Gtk.Label(label=self.input.description)
        label_name.wrap = True
        label_name.set_halign(Gtk.Align.START)
        grid.attach(label_name, 0, 0, 1, 1)

        active = Gtk.CheckButton(label="Active")
        active.set_action_name("app." + self.active.get_name())
        grid.attach(active, 0, 1, 1, 1)

        if len(self.modes) > 1:
            modes = Gtk.ComboBox(model=self.modes)
            modes.set_id_column(0)
            renderer = Gtk.CellRendererText()
            modes.pack_start(renderer, True)
            modes.add_attribute(renderer, "text", 1)
            modes.set_active_id("default")
            modes.connect("changed", self.on_mode_changed)
            grid.attach(modes, 0, 2, 1, 1)

        return grid
