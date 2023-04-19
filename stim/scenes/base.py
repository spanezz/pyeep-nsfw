from __future__ import annotations

from typing import Type

from pyeep.app import check_hub
from pyeep.gtk import Gtk, GtkComponent

SCENES: list[Type["Scene"]] = []


def register(c: Type["Scene"]) -> Type["Scene"]:
    SCENES.append(c)
    return c


class Scene(GtkComponent):
    TITLE: str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # TODO: move the action for the active switch here
        self.active = Gtk.Switch()
        self.active.connect("state-set", self.on_active)

    def build(self) -> Gtk.Expander:
        expander = Gtk.Expander(label=self.TITLE)
        label = expander.get_label_widget()
        # TODO: move backend to __init__
        box = Gtk.Box()
        expander.set_label_widget(box)
        box.append(self.active)
        box.append(label)

        # self.set_title(self.TITLE)
        # self.set_default_size(600, 300)
        return expander

    def on_active(self, switch, state):
        if state:
            self.start()
        else:
            self.pause()

    @check_hub
    def is_active(self):
        return self.active.get_state()

    @check_hub
    def start(self):
        pass

    @check_hub
    def pause(self):
        pass
