from __future__ import annotations

from pyeep.app import Message, check_hub
from pyeep.gtk import GLib, Gtk
from pyeep.messages import EmergencyStop, Shortcut

from .. import messages, output
from .base import Scene, register
from .default import KeyboardShortcutMixin


@register
class Eagerness(KeyboardShortcutMixin, Scene):
    TITLE = "Eagerness"
    BPM_START = 6
    INCREMENT_START = 2

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bpm = Gtk.Adjustment(
                lower=1, upper=600, step_increment=1, page_increment=5, value=self.BPM_START)
        self.bpm.connect("value-changed", self.on_value_changed)
        self.increment = Gtk.Adjustment(
                lower=0, upper=100, step_increment=1, page_increment=5, value=self.INCREMENT_START)
        self.timeout: int | None = None

    def build(self) -> Gtk.Expander:
        expander = super().build()
        grid = Gtk.Grid()
        expander.set_child(grid)

        spinbutton = Gtk.SpinButton()
        spinbutton.set_adjustment(self.bpm)
        grid.attach(spinbutton, 0, 0, 1, 1)

        grid.attach(Gtk.Label(label="times per minute, increase by"), 1, 0, 1, 1)

        spinbutton = Gtk.SpinButton()
        spinbutton.set_adjustment(self.increment)
        grid.attach(spinbutton, 2, 0, 1, 1)

        stop = Gtk.Button(label="Stop!")
        stop.connect("clicked", self.on_stop)
        grid.attach(stop, 0, 1, 4, 1)

        return expander

    @check_hub
    def start(self):
        super().start()
        self.update_timer()

    @check_hub
    def pause(self):
        if self.timeout is not None:
            GLib.source_remove(self.timeout)
            self.timeout = None
        super().pause()

    @check_hub
    def cleanup(self):
        self.pause()
        super().cleanup()

    @check_hub
    def update_timer(self):
        if self.timeout is not None:
            GLib.source_remove(self.timeout)
            self.timeout = None

        value = self.bpm.get_value()
        if value > 0:
            self.timeout = GLib.timeout_add(round(60 / value * 1000), self.on_tick)

    def on_value_changed(self, adjustment):
        if self.is_active:
            self.update_timer()

    def on_stop(self, button):
        self.do_stop()

    def on_tick(self):
        amount = self.increment.get_value()
        self.send(output.IncreaseActivePower(amount=amount))
        return True

    def do_stop(self):
        self.send(output.SetActivePower(power=0))
        self.speed_up()

    def do_speed_up(self):
        self.bpm.set_value(self.bpm.get_value() * 1.2)

    def do_slow_down(self):
        self.bpm.set_value(self.bpm.get_value() / 1.2)

    @check_hub
    def handle_keyboard_shortcut(self, shortcut: str):
        match shortcut:
            case "CYCLE START":
                self.start()
                self.send(messages.Resume())
            case "STOP":
                self.do_stop()
            case "SPEED UP":
                self.do_speed_up()
            case "SLOW DOWN":
                self.do_slow_down()
            case "F+":
                self.increment.set_value(self.increment.get_value() + 1)
            case "F-":
                self.increment.set_value(self.increment.get_value() - 1)
            case "REDO":
                self.bpm.set_value(self.BPM_START)
                self.increment.set_value(self.INCREMENT_START)
                self.send(output.SetActivePower(power=0))
            case _:
                super().handle_keyboard_shortcut(shortcut)

    @check_hub
    def receive(self, msg: Message):
        if not self.is_active:
            return
        match msg:
            case EmergencyStop():
                self.pause()
            case Shortcut():
                self.handle_keyboard_shortcut(msg.command)
