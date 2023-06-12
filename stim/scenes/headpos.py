from __future__ import annotations

import inspect
from typing import Iterator

import numpy

from pyeep.messages import Message
from pyeep.component.base import check_hub, export
from pyeep.component.modes import ModeComponent, ModeInfo
from pyeep.gtk import GLib, Gtk, Gio
from pyeep.outputs.color import SetGroupColor
from pyeep.color import Color

from ..muse2 import HeadMoved, HeadYesNo, HeadGyro
from .base import Scene, SingleGroupScene, SingleGroupPowerScene, register
from .. import dsp


@register
class HeadPosition(SingleGroupPowerScene):
    TITLE = "Head position"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.reference_roll: float | None = None
        self.reference_pitch: float | None = None

        self.control_angle = Gtk.Adjustment(
                value=60, upper=180, step_increment=5, page_increment=10)

        # TODO: replace with a Gtk backend for mode selection
        self.mode: str = "center_zero"
        self.ui_grid_columns = max(self.ui_grid_columns, 3)

    def build(self) -> Gtk.Expander:
        expander = super().build()
        grid = expander.get_child()
        row = grid.max_row

        zero_center = Gtk.CheckButton(label="Zero on center")
        zero_center.connect("toggled", self.set_mode, "center_zero")
        zero_center.set_active(True)
        grid.attach(zero_center, 0, row, height=1)
        row += 1

        mid_center_increase_up = Gtk.CheckButton(label="Middle on center, up increases")
        mid_center_increase_up.set_group(zero_center)
        mid_center_increase_up.connect("toggled", self.set_mode, "center_middle_increase_up")
        grid.attach(mid_center_increase_up, 0, row, height=1)
        row += 1

        mid_center_increase_down = Gtk.CheckButton(label="Middle on center, down increases")
        mid_center_increase_down.set_group(zero_center)
        mid_center_increase_down.connect("toggled", self.set_mode, "center_middle_increase_down")
        grid.attach(mid_center_increase_down, 0, row, height=1)
        row += 1

        max_center = Gtk.CheckButton(label="Max on center")
        max_center.set_group(zero_center)
        max_center.connect("toggled", self.set_mode, "center_max")
        grid.attach(max_center, 0, row, height=1)
        row += 1

        grid.attach(Gtk.Label(label="Control angle"), 0, row, 1, 1)
        control_angle_button = Gtk.SpinButton()
        control_angle_button.set_adjustment(self.control_angle)
        grid.attach(control_angle_button, 1, row, height=1)
        row += 1

        center = Gtk.Button.new_with_label("Recenter")
        center.connect("clicked", self.set_center)
        grid.attach(center, 0, row, height=1)
        row += 1

        return expander

    @check_hub
    def set_mode(self, button, mode: str):
        self.mode = mode

    @check_hub
    def set_center(self, button):
        self.reference_pitch = None
        self.reference_roll = None

    @check_hub
    def receive(self, msg: Message):
        match msg:
            case HeadMoved():
                if self.is_active:
                    if self.reference_roll is None:
                        self.reference_roll = msg.roll

                    if self.reference_pitch is None:
                        self.reference_pitch = msg.pitch

                    # roll_angle = self.reference_roll - roll
                    pitch_angle = self.reference_pitch - msg.pitch
                    control_angle = self.control_angle.get_value()
                    match self.mode:
                        case "center_zero":
                            power = numpy.clip(abs(pitch_angle) * 2 / control_angle, 0, 1)
                        case "center_middle_increase_up":
                            power = numpy.clip(0.5 - pitch_angle * 2 / control_angle, 0, 1)
                        case "center_middle_increase_down":
                            power = numpy.clip(0.5 + pitch_angle * 2 / control_angle, 0, 1)
                        case "center_max":
                            power = numpy.clip(1 - abs(pitch_angle) * 2 / control_angle, 0, 1)
                        case _:
                            self.logger.warning("Unknown mode %r", self.mode)
                            power = 0

                    self.set_power(power)


@register
class Consent(SingleGroupPowerScene):
    TITLE = "Consent"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout: int | None = None

        self.streak_start: HeadYesNo | None = None
        self.streak_last: HeadYesNo | None = None

        self.instant_no = Gio.SimpleAction.new_stateful(
                name=self.name.replace("_", "-") + "-instant_no",
                parameter_type=None,
                state=GLib.Variant.new_boolean(False))
        self.hub.app.gtk_app.add_action(self.instant_no)

        self.decay = Gio.SimpleAction.new_stateful(
                name=self.name.replace("_", "-") + "-decay",
                parameter_type=None,
                state=GLib.Variant.new_boolean(True))
        self.hub.app.gtk_app.add_action(self.decay)

    @check_hub
    def set_active(self, value: bool):
        if not value and self.timeout is not None:
            GLib.source_remove(self.timeout)
            self.timeout = None
        super().set_active(value)

    def _tick(self):
        # Slow decay
        self.increment_power(-0.02)
        return True

    def _reset_timeout(self):
        if self.timeout is not None:
            GLib.source_remove(self.timeout)
            self.timeout = None

        if not self.decay.get_state().get_boolean():
            return

        self.timeout = GLib.timeout_add(500, self._tick)

    def build(self) -> Gtk.Expander:
        expander = super().build()
        grid = expander.get_child()
        row = grid.max_row

        decay = Gtk.ToggleButton(label="Decay")
        decay.set_action_name("app." + self.decay.get_name())
        grid.attach(decay, 0, row, 1, 1)

        instant_no = Gtk.ToggleButton(label="Instant NO")
        instant_no.set_action_name("app." + self.instant_no.get_name())
        grid.attach(instant_no, 1, row, 1, 1)

        return expander

    @check_hub
    def receive(self, msg: Message):
        if not self.is_active:
            return

        match msg:
            case HeadYesNo():
                instant_no = self.instant_no.get_state().get_boolean()

                if msg.intensity < 0.1:
                    return

                if (self.streak_start is None
                        or self.streak_start.gesture != msg.gesture
                        or msg.ts - self.streak_last.ts > 0.3):
                    self.streak_start = msg
                    self.streak_last = msg

                in_streak = round(msg.ts - self.streak_start.ts)
                self.streak_last = msg

                # Time in seconds it takes to reach from min to max at the maximum speed
                match msg.gesture:
                    case "meh":
                        min_time_to_max = 10
                    case "no":
                        min_time_to_max = 2
                        if instant_no and msg.intensity < 0.3:
                            return
                    case "yes":
                        min_time_to_max = 5

                value = msg.intensity / 52 * msg.frames / min_time_to_max
                if value > 0.001:
                    match msg.gesture:
                        case "meh":
                            self.increment_power(-value)
                            self._reset_timeout()
                        case "no":
                            if instant_no:
                                value = 1.0
                            self.increment_power(-value)
                            self._reset_timeout()
                        case "yes":
                            if in_streak:
                                value *= in_streak + 1
                            self.increment_power(value)
                            self._reset_timeout()


class ModeBase:
    """
    Base class for Muse2 data processing modes
    """
    def __init__(self, *, scene: Scene):
        self.scene = scene

    def on_message(self, msg: Message):
        pass


class Dance(ModeBase):
    """
    Pitch/roll
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.input_rate = 52
        self.filter_red = dsp.Butterworth(rate=self.input_rate, cutoff=10)
        self.filter_green = dsp.Butterworth(rate=self.input_rate, cutoff=10)
        self.filter_blue = dsp.Butterworth(rate=self.input_rate, cutoff=10)

    def on_message(self, msg: Message):
        match msg:
            case HeadYesNo():
                value = msg.intensity ** 2

                red = 0
                green = 0
                blue = 0

                match msg.gesture:
                    case "meh":
                        # Meh
                        red = value
                        green = value / 3
                    case "yes":
                        # Yes
                        green = value
                    case "no":
                        # No
                        red = value

                red = self.filter_red(red)
                green = self.filter_green(green)
                blue = self.filter_blue(blue)

                color = Color(
                    red=numpy.clip(red, 0, 1),
                    green=numpy.clip(green, 0, 1),
                    blue=numpy.clip(blue, 0, 1),
                )

                self.scene.send(SetGroupColor(
                    group=self.scene.get_group(),
                    color=color))

            case HeadMoved():
                def norm(val: float, min_angle=0, max_angle=80) -> float:
                    return ((abs(val) - min_angle) / (max_angle - min_angle)) ** 2

                blue = self.filter_blue(norm(msg.pitch, max_angle=40))
                green = self.filter_green(norm(msg.roll, max_angle=40))
                red = self.filter_red(1 - max(blue, green))

                color = Color(
                    red=numpy.clip(red, 0, 1),
                    green=numpy.clip(green, 0, 1),
                    blue=numpy.clip(blue, 0, 1),
                )

                self.scene.send(SetGroupColor(
                    group=self.scene.get_group(),
                    color=color))
            case HeadGyro():
                min_dps = 0.0
                max_dps = 200.0

                def norm(val: float) -> float:
                    return ((abs(val) - min_dps) / (max_dps - min_dps)) ** 2

                for sample in msg.x:
                    red = self.filter_red(norm(sample))
                for sample in msg.y:
                    green = self.filter_green(norm(sample))
                for sample in msg.z:
                    blue = self.filter_blue(norm(sample))

                color = Color(
                    red=numpy.clip(red, 0, 1),
                    green=numpy.clip(green, 0, 1),
                    blue=numpy.clip(blue, 0, 1),
                )

                self.scene.send(SetGroupColor(
                    group=self.scene.get_group(),
                    color=color))
            case _:
                super().on_message(msg)


@register
class ColorDance(ModeComponent, SingleGroupScene):
    TITLE = "Color dance"

    MODES = {
        "default": Dance,
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.modes = Gtk.ListStore(str, str)
        for info in self.list_modes():
            self.modes.append([info.name, info.summary])

    @export
    def set_mode(self, name: str) -> None:
        """
        Set the active mode
        """
        self.mode = self.MODES[name](scene=self)

    def list_modes(self) -> Iterator[ModeInfo, None]:
        """
        List available modes
        """
        for name, value in self.MODES.items():
            yield ModeInfo(name, inspect.getdoc(value))

    @check_hub
    def set_active(self, value: bool):
        super().set_active(value)
        self.send(SetGroupColor(
            group=self.get_group(),
            color=Color(0, 0, 0)))

    @check_hub
    def receive(self, msg: Message):
        if self.is_active:
            self.mode.on_message(msg)

    def build(self) -> Gtk.Expander:
        expander = super().build()
        grid = expander.get_child()

        if len(self.modes) > 1:
            row = grid.max_row
            modes = Gtk.ComboBox(model=self.modes)
            modes.set_id_column(0)
            renderer = Gtk.CellRendererText()
            modes.pack_start(renderer, True)
            modes.add_attribute(renderer, "text", 1)
            modes.set_active_id("default")
            modes.connect("changed", self.on_mode_changed)
            grid.attach(modes, 0, row, 2, 1)

        return expander

    def on_mode_changed(self, combo):
        tree_iter = combo.get_active_iter()
        if tree_iter is not None:
            model = combo.get_model()
            mode = model[tree_iter][0]
            self.set_mode(mode)
