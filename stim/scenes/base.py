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
        self.active.connect("activate", self.on_active)
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

        # self.set_title(self.TITLE)
        # self.set_default_size(600, 300)
        return expander

    def on_active(self, switch, state):
        new_state = not self.active.get_state().get_boolean()
        print("OA", new_state)
        self.active.set_state(GLib.Variant.new_boolean(new_state))
        if new_state:
            self.start()
        else:
            self.pause()

    @check_hub
    def is_active(self) -> bool:
        return self.active.get_state().get_boolean()

    @check_hub
    def start(self):
        pass

    @check_hub
    def pause(self):
        pass
