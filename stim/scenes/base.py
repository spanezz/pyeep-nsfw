from __future__ import annotations

from typing import Type

from pyeep.app import check_hub
from pyeep.gtk import Gtk, GtkComponentExpander

SCENES: list[Type["Scene"]] = []


def register(c: Type["Scene"]) -> Type["Scene"]:
    SCENES.append(c)
    return c


class Scene(GtkComponentExpander):
    TITLE: str

    def __init__(self, **kwargs):
        kwargs.setdefault("label", self.TITLE)
        super().__init__(**kwargs)
        self.build()

    def build(self):
        label = self.get_label_widget()
        self.active = Gtk.Switch()
        self.active.connect("state-set", self.on_active)
        box = Gtk.Box()
        self.set_label_widget(box)
        box.append(self.active)
        box.append(label)

        # self.set_title(self.TITLE)
        # self.set_default_size(600, 300)

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
