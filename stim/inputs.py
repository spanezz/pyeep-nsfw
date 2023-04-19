from __future__ import annotations

import pyeep.aio
from pyeep.gtk import Gio, GLib, Gtk, GtkComponent


class Input(pyeep.app.Component):
    """
    Generic base for output components
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def description(self) -> str:
        return self.name


class InputModel(GtkComponent):
    def __init__(self, *, input: Input, **kwargs):
        kwargs.setdefault("name", "input_model_" + input.name)
        super().__init__(**kwargs)
        self.input = input

        self.active = Gio.SimpleAction.new_stateful(
                name=self.name.replace("_", "-"),
                parameter_type=None,
                state=GLib.Variant.new_boolean(False))
        self.active.connect("activate", self.on_activate)
        self.hub.app.gtk_app.add_action(self.active)

    def is_active(self) -> bool:
        return self.active.get_state().get_boolean()

    def on_activate(self, action, parameter):
        new_state = not self.active.get_state().get_boolean()
        self.active.set_state(GLib.Variant.new_boolean(new_state))

    def build(self) -> Gtk.Box:
        w = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        w.set_hexpand(True)

        label_name = Gtk.Label(label=self.input.description)
        label_name.wrap = True
        w.append(label_name)

        active = Gtk.CheckButton(label="Active")
        active.set_action_name("app." + self.active.get_name())
        w.append(active)

        return w
