from __future__ import annotations

from pyeep.app import Message, check_hub
from pyeep.gtk import GLib, Gtk
from pyeep.messages import Shortcut

from .base import Scene, PowerControl, SceneGrid, register


@register
class FourAxes(Scene):
    TITLE = "Four Axes"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Active by default
        self.active.set_state(GLib.Variant.new_boolean(True))

        self.axes = {
            "x": PowerControl(self, "x", group=1),
            "y": PowerControl(self, "y", group=2),
            "z": PowerControl(self, "z", group=3),
            "a": PowerControl(self, "a", group=4),
        }

        self.ui_grid_columns = 3

    @check_hub
    def receive(self, msg: Message):
        if not self.is_active:
            return
        match msg:
            case Shortcut():
                match msg.command:
                    case "+X":
                        self.axes["x"].increment_power(0.05)
                    case "-X":
                        self.axes["x"].increment_power(-0.05)
                    case "+Y":
                        self.axes["y"].increment_power(0.05)
                    case "-Y":
                        self.axes["y"].increment_power(-0.05)
                    case "+Z":
                        self.axes["z"].increment_power(0.05)
                    case "-Z":
                        self.axes["z"].increment_power(-0.05)
                    case "+A":
                        self.axes["a"].increment_power(0.05)
                    case "-A":
                        self.axes["a"].increment_power(-0.05)

    def build(self) -> Gtk.Expander:
        expander = super().build()
        grid = SceneGrid(max_column=self.ui_grid_columns)
        expander.set_child(grid)

        for axis in self.axes.values():
            axis.attach_to_grid(grid)

        return expander
