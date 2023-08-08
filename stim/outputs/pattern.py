from __future__ import annotations

from typing import Any, Type

import jack
import numpy

from pyeep.component.controller import ControllerWidget
from pyeep.component.aio import AIOComponent
from pyeep.component.base import check_hub, export
from pyeep.component.jack import JackComponent
from pyeep.gtk import Gtk, Gio, GLib
from pyeep.messages import Shutdown, Configure
from pyeep.midisynth import SineWave
from pyeep.outputs.base import OutputController

from ..output import Output


class Channel:
    def __init__(
            self, *,
            name: str,
            osc_freq: float = 1000,
            lfo_freq: float = 1,
            min_level: float = 0,
            max_level: float = 0.3):
        self.name = name
        self.rate: int

        self.osc: SineWave
        self.osc_freq = osc_freq

        self.lfo: SineWave
        self.lfo_freq = lfo_freq

        self.min_level = min_level
        self.max_level = max_level

    def set_rate(self, rate: int):
        self.rate = rate
        self.osc = SineWave(self.rate)
        self.lfo = SineWave(self.rate)

    def make_envelope(self, frames: int) -> numpy.ndarray:
        lfo = numpy.zeros(frames)
        self.lfo.wave(lfo, self.lfo_freq)

        span = self.max_level - self.min_level
        return self.min_level + span / 2 + lfo * span / 2

    def synth(self, frames: int, array: numpy.ndarray):
        envelope = self.make_envelope(frames)
        array.fill(0)
        self.osc.synth(array, self.osc_freq, envelope)


class PatternPlayer(Output, JackComponent, AIOComponent):
    def __init__(self, frequency: float = 1000.0, **kwargs):
        super().__init__(rate=0, **kwargs)
        self.left = Channel(name="pattern_L")
        self.right = Channel(name="pattern_R")

    def get_output_controller(self) -> Type[OutputController]:
        return PatternOutputController

    def set_jack_client(self, jack_client: jack.Client):
        super().set_jack_client(jack_client)
        self.rate = jack_client.samplerate
        self.left.set_rate(self.rate)
        self.right.set_rate(self.rate)
        self.outport_l = self.jack_client.outports.register('pattern_L')
        # print(self.jack_client.inports)
        # print(self.jack_client.outports)
        # print(self.jack_client.get_ports(name_pattern="Built-in Audio Analog Stereo:", is_audio=True, is_input=True))
        self.outport_r = self.jack_client.outports.register('pattern_R')
        # TODO: autoconnect to previously connected ports
        self.outport_l.connect("Built-in Audio Analog Stereo:playback_FL")
        self.outport_r.connect("Built-in Audio Analog Stereo:playback_FR")

    def jack_process(self, frames: int) -> None:
        self.left.synth(frames, self.outport_l.get_array())
        self.right.synth(frames, self.outport_r.get_array())

    @export
    def setup(
            self, *,
            freq_left: float | None = None,
            freq_right: float | None = None,
            lfo_freq_left: float | None = None,
            lfo_freq_right: float | None = None,
            min_level_left: float | None = None,
            min_level_right: float | None = None,
            max_level_left: float | None = None,
            max_level_right: float | None = None):
        if freq_left is not None:
            self.left.osc_freq = freq_left
        if freq_right is not None:
            self.right.osc_freq = freq_right
        if lfo_freq_left is not None:
            self.left.lfo_freq = lfo_freq_left
        if lfo_freq_right is not None:
            self.right.lfo_freq = lfo_freq_right
        if min_level_left is not None:
            self.left.min_level = min_level_left
        if min_level_right is not None:
            self.right.min_level = min_level_right
        if max_level_left is not None:
            self.left.max_level = max_level_left
        if max_level_right is not None:
            self.right.max_level = max_level_right

    @check_hub
    def load_config(self, config: dict[str, Any]):
        print("PATTERN LC")
        super().load_config(config)
        kwargs: dict[str, Any] = {}
        for arg in ("freq_left", "freq_right", "lfo_freq_left", "lfo_freq_right", "min_level_left", "min_level_right"):
            if (val := config.get(arg)) is not None:
                kwargs[arg] = val
        if kwargs:
            print("PATTERN LC", kwargs)
            self.setup(**kwargs)

    @check_hub
    def get_config(self) -> dict[str, Any]:
        res = super().get_config()
        res["frequency_left"] = self.frequency_left
        res["frequency_right"] = self.frequency_right
        res["lfo_freq_left"] = self.pattern.lfo_freq_left
        res["lfo_freq_right"] = self.pattern.lfo_freq_right
        res["min_level_left"] = self.pattern.min_level_left
        res["min_level_right"] = self.pattern.min_level_right
        return res

    async def run(self) -> None:
        while True:
            match (msg := await self.next_message()):
                case Shutdown():
                    break
                case Configure():
                    print("PATTERN CONFIG", msg.config)
                    # TODO: forward config to the controller? Does it exist
                    # yet? Change Hub to enqueue messages for not-yet-existing
                    # components?
                    self.load_config(msg.config)


class PatternOutputController(OutputController):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # TODO: animated targets for the various parameters
        # TODO: Wave shape left (sine, saw, square)
        # TODO: Wave shape right (sine, saw, square)

        self.freq_left = Gtk.Adjustment(
                value=self.output.left.osc_freq,
                lower=100,
                upper=2000,
                step_increment=10,
                page_increment=100,
                page_size=0)
        self.freq_left.connect("value_changed", self.on_change)

        self.freq_right = Gtk.Adjustment(
                value=self.output.right.osc_freq,
                lower=100,
                upper=2000,
                step_increment=10,
                page_increment=100,
                page_size=0)
        self.freq_right.connect("value_changed", self.on_change)

        self.lfo_freq_left = Gtk.Adjustment(
                value=self.output.left.lfo_freq,
                lower=0,
                upper=10,
                step_increment=0.1,
                page_increment=1,
                page_size=0)
        self.lfo_freq_left.connect("value_changed", self.on_change)

        self.lfo_freq_right = Gtk.Adjustment(
                value=self.output.right.lfo_freq,
                lower=0,
                upper=10,
                step_increment=0.1,
                page_increment=1,
                page_size=0)
        self.lfo_freq_right.connect("value_changed", self.on_change)

        self.min_level_left = Gtk.Adjustment(
                value=self.output.left.min_level,
                lower=0,
                upper=1,
                step_increment=0.05,
                page_increment=0.1,
                page_size=0)
        self.min_level_left.connect("value_changed", self.on_change)

        self.min_level_right = Gtk.Adjustment(
                value=self.output.right.min_level,
                lower=0,
                upper=1,
                step_increment=0.05,
                page_increment=0.1,
                page_size=0)
        self.min_level_right.connect("value_changed", self.on_change)

        self.max_level_left = Gtk.Adjustment(
                value=0.3,
                lower=0,
                upper=1,
                step_increment=0.01,
                page_increment=0.1,
                page_size=0)
        self.max_level_left.connect("value_changed", self.on_change)

        self.max_level_right = Gtk.Adjustment(
                value=0.3,
                lower=0,
                upper=1,
                step_increment=0.01,
                page_increment=0.1,
                page_size=0)
        self.max_level_right.connect("value_changed", self.on_change)

        self.auto_apply = Gio.SimpleAction.new_stateful(
                name=self.name.replace("_", "-") + "-auto-apply",
                parameter_type=None,
                state=GLib.Variant.new_boolean(False))
        self.hub.app.gtk_app.add_action(self.auto_apply)

    # @check_hub
    # def set_paused(self, paused: bool):
    #     """
    #     Enter/exit pause mode
    #     """
    #     super().set_paused(paused)

    #     if paused:
    #         self.output.set_power(0)
    #     else:
    #         power = self.power.get_value() / 100.0
    #         self.output.set_power(power)

    # @check_hub
    # def emergency_stop(self):
    #     self.power.set_value(0)
    #     self.power_levels.clear()
    #     super().emergency_stop()

    # @check_hub
    # def receive(self, msg: Message):
    #     match msg:
    #         case SetGroupPower():
    #             if self.in_group(msg.group):
    #                 self.set_source_power(msg.src, msg.power)
    #         case IncreaseGroupPower():
    #             if self.in_group(msg.group):
    #                 match msg.amount:
    #                     case PowerAnimation():
    #                         self.power_animator.start(msg.amount)
    #         case _:
    #             super().receive(msg)

    def on_apply(self, button):
        self.output.setup(
            freq_left=self.freq_left.get_value(),
            freq_right=self.freq_right.get_value(),
            lfo_freq_left=self.lfo_freq_left.get_value(),
            lfo_freq_right=self.lfo_freq_right.get_value(),
            min_level_left=self.min_level_left.get_value(),
            min_level_right=self.min_level_right.get_value(),
            max_level_left=self.max_level_left.get_value(),
            max_level_right=self.max_level_right.get_value(),
        )

    def on_change(self, element):
        if not self.auto_apply.get_state().get_boolean():
            return
        self.on_apply(None)

    def build(self) -> ControllerWidget:
        cw = super().build()

        cw.grid.attach(Gtk.Label(label="Left"), 1, 2, 2, 1)
        cw.grid.attach(Gtk.Label(label="Right"), 3, 2, 2, 1)
        cw.grid.attach(Gtk.Label(label="Freq"), 0, 3, 1, 1)
        cw.grid.attach(Gtk.Label(label="LFO"), 0, 4, 1, 1)
        cw.grid.attach(Gtk.Label(label="Min"), 0, 5, 1, 1)
        cw.grid.attach(Gtk.Label(label="Max"), 0, 6, 1, 1)

        freq_left = Gtk.SpinButton(
            adjustment=self.freq_left,
            digits=1)
        cw.grid.attach(freq_left, 1, 3, 2, 1)

        freq_right = Gtk.SpinButton(
            adjustment=self.freq_right,
            digits=1)
        cw.grid.attach(freq_right, 3, 3, 2, 1)

        lfo_freq_left = Gtk.SpinButton(
            adjustment=self.lfo_freq_left,
            digits=1)
        cw.grid.attach(lfo_freq_left, 1, 4, 2, 1)

        lfo_freq_right = Gtk.SpinButton(
            adjustment=self.lfo_freq_right,
            digits=1)
        cw.grid.attach(lfo_freq_right, 3, 4, 2, 1)

        min_level_left = Gtk.SpinButton(
            adjustment=self.min_level_left,
            digits=2)
        cw.grid.attach(min_level_left, 1, 5, 2, 1)

        min_level_right = Gtk.SpinButton(
            adjustment=self.min_level_right,
            digits=2)
        cw.grid.attach(min_level_right, 3, 5, 2, 1)

        max_level_left = Gtk.SpinButton(
            adjustment=self.max_level_left,
            digits=2)
        cw.grid.attach(max_level_left, 1, 6, 2, 1)

        max_level_right = Gtk.SpinButton(
            adjustment=self.max_level_right,
            digits=2)
        cw.grid.attach(max_level_right, 3, 6, 2, 1)

        pulse = Gtk.Button(label="Apply")
        pulse.connect("clicked", self.on_apply)
        cw.grid.attach(pulse, 0, 7, 1, 1)

        decay = Gtk.ToggleButton(label="Auto apply")
        decay.set_action_name("app." + self.auto_apply.get_name())
        cw.grid.attach(decay, 1, 7, 1, 1)

        return cw
