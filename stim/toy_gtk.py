from __future__ import annotations

# import queue

# import pyeep.gtk
from pyeep.gtk import Gtk, GtkComponentBox
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
#
#     def process_queues(self):
#         while not self.queue.empty():
#             self.append(self.queue.get())
#         return False


class ToyView(GtkComponentBox):
    def __init__(self, *, actuator: toy.Actuator, toys_view: "ToysView", **kwargs):
        kwargs.setdefault("name", "tv_" + actuator.name)
        super().__init__(**kwargs)

        self.actuator = actuator
        self.toys_view = toys_view

        self.set_hexpand(True)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.box.set_hexpand(True)
        self.append(self.box)

        self.label_name = Gtk.Label(label=actuator.actuator._device.name + "\n" + actuator.name)
        self.box.append(self.label_name)

        self.active = Gtk.CheckButton(label="Active")
        self.active.connect("toggled", self.on_active)
        self.box.append(self.active)

        if self.toys_view.toy_views:
            self.active.set_group(self.toys_view.toy_views[0].active)

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
        self.box.append(self.power)
        self.adjustment = self.power.get_adjustment()

        self.power.connect("value_changed", self.on_power)
        self.last_value: float = 0.0
        self.value_override: float | None = None

    def on_active(self, button):
        if button.get_active():
            self.toys_view.active = self

    def is_active(self) -> bool:
        return self.active.get_active()

    def set_value(self, value: float):
        if self.value_override is not None:
            self.adjustment.set_value(self.value_override)
        else:
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
                        self.value_override = None
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
                            self.value_override = 100
                            self.set_value(self.last_value)
                    case "-Z":
                        if self.is_active():
                            self.value_override = None
                            self.set_value(self.last_value)
                    case "F+":
                        if self.is_active():
                            self.add_value(1)
                    case "F-":
                        if self.is_active():
                            self.add_value(-1)

    def on_power(self, adj):
        val = round(adj.get_value())
        self.toys_view.send(toy.SetPower(actuator=self.actuator.actuator, power=val / 100.0))


class ToysView(GtkComponentBox):
    def __init__(self, **kwargs):
        kwargs["orientation"] = Gtk.Orientation.VERTICAL
        super().__init__(**kwargs)
        self.toy_views: list[ToyView] = []
        self.active: ToyView | None = None
        self.set_hexpand(True)

        self.scan = Gtk.ToggleButton.new_with_label("Device scan")
        self.scan.connect("toggled", self.on_scan_toggled)
        self.append(self.scan)

        self.toybox = Gtk.Box()
        self.append(self.toybox)

    def get_active_index(self) -> int:
        for idx, tv in enumerate(self.toy_views):
            if tv.is_active():
                return idx
        return 0

    def on_scan_toggled(self, toggle):
        if self.scan.get_active():
            self.send(toy.ScanRequest(dst="toys", scan=True))
        else:
            self.send(toy.ScanRequest(dst="toys", scan=False))

    def receive(self, msg: toy.Message):
        match msg:
            case toy.NewDevice():
                tv = self.hub.app.add_component(ToyView, actuator=msg.actuator, toys_view=self)
                if not self.toy_views:
                    tv.active.set_active(True)
                    self.active = tv
                self.toy_views.append(tv)
                self.toybox.append(tv)
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
