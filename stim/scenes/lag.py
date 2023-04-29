from __future__ import annotations

import functools

from pyeep.app import check_hub, Message
from pyeep.gtk import GLib, Gtk

from .. import output, keyboards
from .base import Scene, register


@register
class Lag(Scene):
    TITLE = "Lag"
    LAG_START = 2

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.lag = Gtk.Adjustment(
                lower=0, upper=10, step_increment=1, page_increment=2, value=self.LAG_START)
        self.timeout: int | None = None

    def build(self) -> Gtk.Expander:
        expander = super().build()
        grid = Gtk.Grid()
        expander.set_child(grid)

        spinbutton = Gtk.SpinButton()
        spinbutton.set_adjustment(self.lag)
        grid.attach(spinbutton, 0, 0, 1, 1)

        grid.attach(Gtk.Label(label="seconds of lag per minute, increase by"), 1, 0, 1, 1)

        return expander

    def stop(self):
        self.send(output.SetActivePower(power=0))
        self.slow_down()

    def speed_up(self):
        self.lag.set_value(self.lag.get_value() - 1)

    def slow_down(self):
        self.lag.set_value(self.lag.get_value() + 1)

    @check_hub
    def _process_cnc_command(self, msg: keyboards.CncCommand):
        if not self.is_active:
            return False
        match msg.command:
            case "STOP":
                self.stop()
            case "SPEED UP":
                self.speed_up()
            case "SLOW DOWN":
                self.slow_down()
            case "CYCLE START":
                self.lag.set_value(self.LAG_START)
                self.send(output.SetActivePower(power=0))
            case "+X":
                self.send(output.IncreaseActivePower(amount=+5))
            case "-X":
                self.send(output.IncreaseActivePower(amount=-5))
        return False

    @check_hub
    def receive(self, msg: Message):
        if not self.is_active():
            return
        match msg:
            case keyboards.CncCommand():
                lag = self.lag.get_value()
                if lag == 0:
                    self._process_cnc_command(msg)
                else:
                    self.timeout = GLib.timeout_add(lag * 1000, functools.partial(self._process_cnc_command, msg))
