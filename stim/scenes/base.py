from __future__ import annotations

from typing import Type

from pyeep.app import check_hub
from pyeep.gtk import Gio, GLib, Gtk, GtkComponent

SCENES: list[Type["Scene"]] = []


def register(c: Type["Scene"]) -> Type["Scene"]:
    SCENES.append(c)
    return c


class Scene(GtkComponent):
    TITLE: str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.active = Gio.SimpleAction.new_stateful(
                name=self.name.replace("_", "-") + "-active",
                parameter_type=None,
                state=GLib.Variant.new_boolean(False))
        self.active.connect("change-state", self.on_active_changed)
        self.hub.app.gtk_app.add_action(self.active)

    def build(self) -> Gtk.Expander:
        expander = Gtk.Expander(label=self.TITLE)
        label = expander.get_label_widget()

        box = Gtk.Box()
        expander.set_label_widget(box)

        active = Gtk.Switch()
        active.set_action_name("app." + self.active.get_name())

        box.append(active)
        box.append(label)

        return expander

    def on_active_changed(self, switch, value):
        new_state = not self.active.get_state().get_boolean()
        self.set_active(new_state)

    @property
    @check_hub
    def is_active(self) -> bool:
        return self.active.get_state().get_boolean()

    @check_hub
    def set_active(self, value: bool):
        self.active.set_state(GLib.Variant.new_boolean(value))

    @check_hub
    def cleanup(self):
        self.set_active(False)
        super().cleanup()


class SingleGroupScene(Scene):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Output group
        self.group = Gtk.Adjustment(
                value=1,
                lower=1,
                upper=99,
                step_increment=1,
                page_increment=1,
                page_size=0)

    def get_group(self) -> int:
        return self.group.get_value()

    def build(self) -> Gtk.Expander:
        expander = super().build()
        grid = Gtk.Grid()
        expander.set_child(grid)

        grid.attach(Gtk.Label(label="Output group"), 0, 0, 1, 1)

        group = Gtk.SpinButton(adjustment=self.group, climb_rate=1.0, digits=0)
        grid.attach(group, 1, 0, 1, 1)

        return expander
