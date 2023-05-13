from __future__ import annotations

from typing import Type

from pyeep.app import check_hub
from pyeep.gtk import Gio, GLib, Gtk, GtkComponent

from .. import output

SCENES: list[Type["Scene"]] = []


def register(c: Type["Scene"]) -> Type["Scene"]:
    SCENES.append(c)
    return c


class SceneGrid(Gtk.Grid):
    REST = -1

    def __init__(self, *, max_column: int = 1, max_row: int = 1, **kwargs):
        super().__init__(**kwargs)
        self.max_column = max_column
        self.max_row = max_row

    def attach(self, child: Gtk.Widget, column: int, row: int, width: int = REST, height: int = REST):
        if width == self.REST:
            width = self.max_column - column
        if height == self.REST:
            height = self.max_row - row
        super().attach(child, column, row, width, height)
        if (mrow := row + height) > self.max_row:
            self.max_row = mrow
        if (mcolumn := column + width) > self.max_column:
            self.max_column = mcolumn


class Scene(GtkComponent):
    TITLE: str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.active = Gio.SimpleAction.new_stateful(
                name=self.name.replace("_", "-") + "-active",
                parameter_type=None,
                state=GLib.Variant.new_boolean(False))
        self.active.connect("change-state", self.on_active_changed)
        self.hub.app.gtk_app.add_action(self.active)

    def build(self) -> Gtk.Expander:
        expander = Gtk.Expander(label=self.TITLE)
        expander.set_margin_bottom(10)
        label = expander.get_label_widget()

        box = Gtk.Box()
        expander.set_label_widget(box)

        active = Gtk.Switch()
        active.set_action_name("app." + self.active.get_name())

        box.append(active)
        box.append(label)

        return expander

    def on_active_changed(self, switch, value):
        new_state = not self.active.get_state().get_boolean()
        self.set_active(new_state)

    @property
    @check_hub
    def is_active(self) -> bool:
        return self.active.get_state().get_boolean()

    @check_hub
    def set_active(self, value: bool):
        self.active.set_state(GLib.Variant.new_boolean(value))

    @check_hub
    def cleanup(self):
        self.set_active(False)
        super().cleanup()


class PowerControl:
    def __init__(self, scene: Scene, name: str, group: int = 1):
        self.scene = scene
        self.name = name

        # Output group
        self.group = Gtk.Adjustment(
                value=group,
                lower=1,
                upper=99,
                step_increment=1,
                page_increment=1,
                page_size=0)

        # Power for the group
        self.power = Gtk.Adjustment(
                value=0,
                lower=0,
                upper=100,
                step_increment=5,
                page_increment=10,
                page_size=0)
        self.power.connect("value_changed", self.on_power)

    def on_power(self, adj):
        """
        Manually set this scene's power
        """
        val = round(adj.get_value())
        self.scene.send(output.SetGroupPower(group=self.get_group(), power=val / 100.0))

    def get_group(self) -> int:
        return self.group.get_value()

    def increment_power(self, value: float):
        self.power.set_value(
                self.power.get_value() + value * 100.0)

    def set_power(self, value: float):
        self.power.set_value(value * 100.0)

    def attach_to_grid(self, grid: SceneGrid):
        power = Gtk.Scale(
                orientation=Gtk.Orientation.HORIZONTAL,
                adjustment=self.power)
        power.set_digits(2)
        power.set_draw_value(False)
        power.set_hexpand(True)
        for mark in (25, 50, 75):
            power.add_mark(
                value=mark,
                position=Gtk.PositionType.BOTTOM,
                markup=None
            )

        row = grid.max_row

        grid.attach(power, 0, row, grid.max_column - 1, 1)

        group = Gtk.SpinButton(adjustment=self.group, climb_rate=1.0, digits=0)
        group.set_tooltip_text("Output group")

        grid.attach(group, grid.max_column - 1, row, 1, 1)


class SingleGroupScene(Scene):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Output group
        self.group = Gtk.Adjustment(
                value=1,
                lower=1,
                upper=99,
                step_increment=1,
                page_increment=1,
                page_size=0)
        self.ui_grid_columns = 2

    def get_group(self) -> int:
        return self.group.get_value()

    def build(self) -> Gtk.Expander:
        expander = super().build()
        grid = SceneGrid(max_column=self.ui_grid_columns)
        expander.set_child(grid)

        grid.attach(Gtk.Label(label="Output group"), 0, 0, self.ui_grid_columns - 1, 1)

        group = Gtk.SpinButton(adjustment=self.group, climb_rate=1.0, digits=0)
        grid.attach(group, self.ui_grid_columns - 1, 0, 1, 1)

        return expander


class SingleGroupPowerScene(SingleGroupScene):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.power = Gtk.Adjustment(
                value=0,
                lower=0,
                upper=100,
                step_increment=5,
                page_increment=10,
                page_size=0)
        self.power.connect("value_changed", self.on_power)

    @check_hub
    def on_power(self, adj):
        """
        Manually set this scene's power
        """
        val = round(adj.get_value())
        self.send(output.SetGroupPower(group=self.get_group(), power=val / 100.0))

    @check_hub
    def increment_power(self, value: float):
        self.power.set_value(
                self.power.get_value() + value * 100.0)

    @check_hub
    def set_power(self, value: float):
        self.power.set_value(value * 100.0)

    def build(self) -> Gtk.Expander:
        expander = super().build()
        grid = expander.get_child()
        row = grid.max_row

        power = Gtk.Scale(
                orientation=Gtk.Orientation.HORIZONTAL,
                adjustment=self.power)
        power.set_digits(2)
        power.set_draw_value(False)
        power.set_hexpand(True)
        for mark in (25, 50, 75):
            power.add_mark(
                value=mark,
                position=Gtk.PositionType.BOTTOM,
                markup=None
            )
        grid.attach(power, 0, row, height=1)

        return expander
