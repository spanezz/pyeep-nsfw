from __future__ import annotations

import random
from typing import Any

from pyeep import animation
from pyeep.component.base import check_hub
from pyeep.gtk import GLib, Gtk
from pyeep.outputs.power import IncreaseGroupPower
from ..messages.message import Message
from ..messages.input import EmergencyStop, Shortcut

from .base import Scene, register
from .default import KeyboardShortcutMixin


@register
class Random(Scene):
    TITLE = "Random"
    OUTPUTS = 3

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # self.lag = Gtk.Adjustment(lower=0.0, upper=10.0, step_increment=0.5, page_increment=2.0, value=self.LAG_START)
        self.timeout: int | None = None

    @check_hub
    def set_active(self, value: bool):
        if not value:
            if self.timeout is not None:
                GLib.source_remove(self.timeout)
                self.timeout = None
        else:
            if self.timeout is None:
                self.timeout = GLib.timeout_add(1000, self.do_something)
        super().set_active(value)

    def build(self) -> Gtk.Expander:
        expander = super().build()
        # grid = expander.get_child()
        # row = grid.max_row

        # spinbutton = Gtk.SpinButton()
        # spinbutton.set_adjustment(self.lag)
        # spinbutton.set_digits(1)
        # grid.attach(spinbutton, 0, row, height=1)

        # grid.attach(Gtk.Label(label="seconds of lag"), 1, row, height=1)

        return expander

    @check_hub
    def do_something(self):
        group = random.randint(0, self.OUTPUTS)
        dice_roll = random.randint(0, 10)
        match dice_roll:
            case 0 | 1 | 2 | 3:
                print("DO NOTHING", group)
                pass
            case 4 | 5 | 6 | 7 | 8 | 9:
                power = random.randint(0, 100) / 100.0
                duration = random.randint(0, 100) / 10.0
                print("BURST", group, power, duration)
                self.send(IncreaseGroupPower(group=group, amount=animation.PowerPulse(power=power, duration=duration)))

        return True
