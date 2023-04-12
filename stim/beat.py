from __future__ import annotations

from pyeep.gtk import GtkComponentBox, Gtk, GLib
from pyeep.app import Message


class SetBpm(Message):
    def __init__(self, *, bpm: float, **kwargs):
        super().__init__(**kwargs)
        self.bpm = bpm


class Beat(Message):
    pass


class BpmView(GtkComponentBox):
    def __init__(self, **kwargs):
        kwargs.setdefault("name", "bpm")
        super().__init__(**kwargs)
        self.adjustment = Gtk.Adjustment(lower=0, upper=300, step_increment=1, page_increment=10)
        self.spinbutton = Gtk.SpinButton()
        self.spinbutton.set_adjustment(self.adjustment)
        self.spinbutton.connect("value-changed", self.on_value_changed)
        self.append(self.spinbutton)
        self.timeout: int | None = None

    def on_value_changed(self, button):
        value = self.adjustment.get_value()
        self.send(SetBpm(bpm=value))

        if self.timeout is not None:
            GLib.source_remove(self.timeout)
            self.timeout = None

        if value > 0:
            self.timeout = GLib.timeout_add_seconds(60/value, self.on_beat)

    def on_beat(self):
        self.send(Beat())
        return True
