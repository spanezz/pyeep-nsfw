from __future__ import annotations

import queue

import pyeep.gtk
from pyeep.gtk import Gtk, GtkComponent
# from . import lovense, toy, cnc
from . import toy, cnc


# class LovenseCommandLogView(pyeep.gtk.LogView):
#     def __init__(self, max_lines: int = 10):
#         super().__init__(max_lines)
#         self.queue: queue.Queue[str] = queue.Queue()
#
#     def attach(self, toy: lovense.Lovense):
#         toy.notify_command = self.on_command
#
#     def on_command(self, cmd):
#         # Executed in the aio thread
#         self.queue.put(cmd)
#         pyeep.gtk.GLib.idle_add(self.process_queues)
 
#     def process_queues(self):
#         while not self.queue.empty():
#             self.append(self.queue.get())
#         return False


class ToyView(GtkComponent, Gtk.Box):
    def __init__(self, *, actuator: toy.Actuator, toys_view: "ToysView", **kwargs):
        kwargs.setdefault("name", "tv_" + actuator.name)
        GtkComponent.__init__(self, **kwargs)
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL)
        self.actuator = actuator
        self.toys_view = toys_view
        self.label_name = Gtk.Label(label=actuator.actuator._device.name + "\n" + actuator.name)
        self.pack_start(self.label_name, False, False, 0)

        if self.toys_view.toy_views:
            active_radio_group = self.toys_view.toy_views[0].active
        else:
            active_radio_group = None
        self.active = Gtk.RadioButton.new_with_label_from_widget(active_radio_group, "Active")
        self.pack_start(self.active, False, False, 0)

        self.power = Gtk.Scale.new_with_range(
                orientation=Gtk.Orientation.HORIZONTAL,
                min=0,
                max=100,
                step=5)
        self.power.set_digits(2)
        self.power.set_draw_value(False)
        for mark in (25, 50, 75):
            self.power.add_mark(
                value=mark,
                position=Gtk.PositionType.BOTTOM,
                markup=None
            )
        self.pack_start(self.power, False, False, 0)
        self.adjustment = self.power.get_adjustment()

        self.power.connect("value_changed", self.on_power)
        self.last_value: float = 0.0

    def is_active(self) -> bool:
        return self.active.get_active()

    def set_value(self, value: float):
        self.adjustment.set_value(value)
        self.last_value = value

    def add_value(self, value: float):
        self.set_value(
            self.adjustment.get_value() + value)

    def receive(self, msg: toy.Message):
        match msg:
            case cnc.CncCommand():
                match msg.command:
                    case "EMERGENCY":
                        self.set_value(0)
                    case "STOP":
                        if self.is_active():
                            self.set_value(0)
                    case "SPEED UP":
                        if self.is_active():
                            self.add_value(
                                self.adjustment.get_minimum_increment())
                    case "SLOW DOWN":
                        if self.is_active():
                            self.add_value(
                                -self.adjustment.get_minimum_increment())
                    case "+Z":
                        if self.is_active():
                            self.adjustment.set_value(100)
                    case "-Z":
                        if self.is_active():
                            self.adjustment.set_value(self.last_value)
                    case "F+":
                        if self.is_active():
                            self.add_value(1)
                    case "F-":
                        if self.is_active():
                            self.add_value(-1)

    def on_power(self, adj):
        val = round(adj.get_value())
        self.toys_view.send(toy.SetPower(actuator=self.actuator.actuator, power=val / 100.0))


class ToysView(GtkComponent, Gtk.Box):
    def __init__(self, **kwargs):
        GtkComponent.__init__(self, **kwargs)
        Gtk.Box.__init__(self)
        self.toy_views: list[ToyView] = []

    def get_active_index(self) -> int:
        for idx, tv in enumerate(self.toy_views):
            if tv.is_active():
                return idx
        return 0

    def receive(self, msg: toy.Message):
        match msg:
            case toy.NewDevice():
                tv = self.hub.app.add_component(ToyView, actuator=msg.actuator, toys_view=self)
                self.toy_views.append(tv)
                self.pack_start(tv, True, True, 0)
                self.show_all()
            case cnc.CncCommand():
                match msg.command:
                    case "+A":
                        new_active = self.get_active_index() + 1
                        if new_active >= len(self.toy_views):
                            new_active = 0
                        self.toy_views[new_active].active.set_active(True)
                    case "-A":
                        new_active = self.get_active_index() - 1
                        if new_active < 0:
                            new_active = len(self.toy_views) - 1
                        self.toy_views[new_active].active.set_active(True)
