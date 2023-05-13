from __future__ import annotations

import functools

from pyeep.app import Message, check_hub
from pyeep.gtk import GLib, Gtk
from pyeep.messages import Shortcut, EmergencyStop

from .base import SingleGroupScene, register
from .default import KeyboardShortcutMixin


@register
class Lag(KeyboardShortcutMixin, SingleGroupScene):
    TITLE = "Lag"
    LAG_START = 1.5

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.lag = Gtk.Adjustment(
                lower=0.0, upper=10.0, step_increment=0.5, page_increment=2.0, value=self.LAG_START)
        self.timeout: int | None = None

    @check_hub
    def set_active(self, value: bool):
        if not value:
            if self.timeout is not None:
                GLib.source_remove(self.timeout)
                self.timeout = None
        super().set_active(value)

    def build(self) -> Gtk.Expander:
        expander = super().build()
        grid = expander.get_child()

        spinbutton = Gtk.SpinButton()
        spinbutton.set_adjustment(self.lag)
        spinbutton.set_digits(1)
        grid.attach(spinbutton, 0, 1, 1, 1)

        grid.attach(Gtk.Label(label="seconds of lag"), 1, 1, 1, 1)

        return expander

    def speed_up(self):
        self.lag.set_value(self.lag.get_value() - 0.5)

    def slow_down(self):
        self.lag.set_value(self.lag.get_value() + 0.5)

    @check_hub
    def handle_keyboard_shortcut(self, shortcut: str):
        if not self.is_active:
            return
        match shortcut:
            case "SPEED UP":
                self.speed_up()
            case "SLOW DOWN":
                self.slow_down()
            case "REDO":
                self.lag.set_value(self.LAG_START)
            case _:
                super().handle_keyboard_shortcut(shortcut)
        return False

    @check_hub
    def receive(self, msg: Message):
        if not self.is_active:
            return
        match msg:
            case EmergencyStop():
                self.lag.set_value(self.LAG_START)
            case Shortcut():
                lag = self.lag.get_value()
                if lag == 0:
                    self.handle_keyboard_shortcut(msg.command)
                else:
                    self.timeout = GLib.timeout_add(
                            lag * 1000,
                            functools.partial(self.handle_keyboard_shortcut, msg.command))
