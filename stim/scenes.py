from __future__ import annotations

from pyeep.app import check_hub
from pyeep.gtk import GLib, Gtk, GtkComponentExpander

from . import output


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


class Eagerness(Scene):
    TITLE = "Eagerness"

    def build(self):
        super().build()
        self.grid = Gtk.Grid()
        self.set_child(self.grid)

        self.bpm = Gtk.Adjustment(lower=1, upper=600, step_increment=1, page_increment=5, value=1)
        self.increment = Gtk.Adjustment(lower=0, upper=100, step_increment=1, page_increment=5, value=2)

        spinbutton = Gtk.SpinButton()
        spinbutton.set_adjustment(self.bpm)
        spinbutton.connect("value-changed", self.on_value_changed)
        self.grid.attach(spinbutton, 0, 0, 1, 1)

        self.grid.attach(Gtk.Label(label="times per minute, increase by"), 1, 0, 1, 1)

        spinbutton = Gtk.SpinButton()
        spinbutton.set_adjustment(self.increment)
        self.grid.attach(spinbutton, 2, 0, 1, 1)

        stop = Gtk.Button(label="Stop!")
        stop.connect("clicked", self.on_stop)
        self.grid.attach(stop, 0, 1, 4, 1)

        self.timeout: int | None = None

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

    def on_value_changed(self, button):
        if self.is_active():
            self.update_timer()

    def on_stop(self, button):
        self.send(output.SetActivePower(power=0))
        self.bpm.set_value(self.bpm.get_value() * 1.2)

    def on_tick(self):
        amount = self.increment.get_value()
        self.send(output.IncreaseActivePower(amount=amount))
        return True
