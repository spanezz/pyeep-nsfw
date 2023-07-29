from __future__ import annotations

from typing import Type

import jack
import numpy

from pyeep.component.controller import ControllerWidget
from pyeep.component.aio import AIOComponent
from pyeep.component.base import export, check_hub
from pyeep.component.jack import JackComponent
from pyeep.gtk import GLib, Gtk
from pyeep.messages import Message, Shutdown
from pyeep.midisynth import SineWave
from pyeep.outputs.base import OutputController

from ..output import Output


class Pattern:
    def __init__(self):
        self.rate: int

    def set_rate(self, rate: int):
        self.rate = rate

    def make_envelopes(self, frames: int) -> tuple[numpy.ndarray, numpy.ndarray]:
        # TODO: pattern generation for envelopes
        dummy = numpy.full(frames, 0.5, dtype=numpy.float64)
        return dummy, dummy


class Pan(Pattern):
    def __init__(self, freq: float, val_min: float = 0.1):
        super().__init__()
        self.freq = freq
        self.val_min = val_min
        self.lfo: SineWave

    def set_rate(self, rate: int):
        super().set_rate(rate)
        self.lfo = SineWave(self.rate)

    def make_envelopes(self, frames: int) -> tuple[numpy.ndarray, numpy.ndarray]:
        lfo = numpy.zeros(frames)
        self.lfo.wave(lfo, self.freq)

        left = numpy.clip(0.5 + lfo / 2, self.val_min, 1)
        right = numpy.clip(0.5 - lfo / 2, self.val_min, 1)

        return left, right


class Pan2(Pattern):
    def __init__(
            self, *,
            lfo_freq_left: float,
            lfo_freq_right: float,
            min_level_left: float = 0.1,
            min_level_right: float = 0.1):
        super().__init__()
        self.lfo_freq_left = lfo_freq_left
        self.lfo_freq_right = lfo_freq_right
        self.min_level_left = min_level_left
        self.min_level_right = min_level_right
        self.lfo_left: SineWave
        self.lfo_right: SineWave

    def set_rate(self, rate: int):
        super().set_rate(rate)
        self.lfo_left = SineWave(self.rate)
        self.lfo_right = SineWave(self.rate)

    def make_envelopes(self, frames: int) -> tuple[numpy.ndarray, numpy.ndarray]:
        lfo_left = numpy.zeros(frames)
        lfo_right = numpy.zeros(frames)
        self.lfo_left.wave(lfo_left, self.lfo_freq_left)
        self.lfo_right.wave(lfo_right, self.lfo_freq_right)

        left_range = 1 - self.min_level_left
        left = self.min_level_left + left_range / 2 + lfo_left * left_range / 2

        right_range = 1 - self.min_level_right
        right = self.min_level_right + right_range / 2 + lfo_right * right_range / 2

        return left, right


class PatternPlayer(Output, JackComponent, AIOComponent):
    def __init__(self, frequency: float = 1000.0, **kwargs):
        super().__init__(rate=0, **kwargs)
        self.sine_left: SineWave
        self.sine_right: SineWave
        self.frequency_left = frequency
        self.frequency_right = frequency
        self.pattern: Pattern | None = None

    def get_output_controller(self) -> Type[OutputController]:
        return PatternOutputController

    def set_jack_client(self, jack_client: jack.Client):
        super().set_jack_client(jack_client)
        self.rate = jack_client.samplerate
        self.sine_left = SineWave(self.rate)
        self.sine_right = SineWave(self.rate)
        self.outport_l = self.jack_client.outports.register('pattern_L')
        # print(self.jack_client.inports)
        # print(self.jack_client.outports)
        # print(self.jack_client.get_ports(name_pattern="Built-in Audio Analog Stereo:", is_audio=True, is_input=True))
        self.outport_r = self.jack_client.outports.register('pattern_R')
        # TODO: autoconnect to previously connected ports
        # self.set_pattern(Pan(freq=3))
        # TODO: restore settings from last run
        self.set_pattern(Pan2(lfo_freq_left=2, lfo_freq_right=1, min_level_right=0.4))
        self.outport_l.connect("Built-in Audio Analog Stereo:playback_FL")
        self.outport_r.connect("Built-in Audio Analog Stereo:playback_FR")

    def set_pattern(self, pattern: Pattern):
        self.pattern = pattern
        self.pattern.set_rate(self.rate)

    def jack_process(self, frames: int) -> None:
        if self.pattern is None:
            return

        envelope_l, envelope_r = self.pattern.make_envelopes(frames)

        array_l = self.outport_l.get_array()
        array_l.fill(0)
        self.sine_left.synth(array_l, self.frequency_left, envelope_l)

        array_r = self.outport_r.get_array()
        array_r.fill(0)
        self.sine_right.synth(array_r, self.frequency_right, envelope_r)

    @export
    def setup(
            self, *,
            freq_left: float,
            freq_right: float,
            lfo_freq_left: float,
            lfo_freq_right: float,
            min_level_left: float,
            min_level_right: float):
        self.frequency_left = freq_left
        self.frequency_right = freq_right
        self.pattern.lfo_freq_left = lfo_freq_left
        self.pattern.lfo_freq_right = lfo_freq_right
        self.pattern.min_level_left = min_level_left
        self.pattern.min_level_right = min_level_right

    async def run(self) -> None:
        while True:
            msg = await self.next_message()
            match msg:
                case Shutdown():
                    break


class PatternOutputController(OutputController):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Frequency left (default 1000.0)
        # Frequency right (default 1000.0)
        # Wave shape left (sine, saw)
        # Wave shape right (sine, saw)
        # LFO frequency left
        # LFO frequency right
        # min level left
        # min level right

        self.freq_left = Gtk.Adjustment(
                value=150,
                lower=100,
                upper=2000,
                step_increment=10,
                page_increment=100,
                page_size=0)
        # self.freq_left.connect("value_changed", self.on_freq_left)

        self.freq_right = Gtk.Adjustment(
                value=150,
                lower=100,
                upper=2000,
                step_increment=10,
                page_increment=100,
                page_size=0)

        self.lfo_freq_left = Gtk.Adjustment(
                value=1,
                lower=0,
                upper=10,
                step_increment=0.1,
                page_increment=1,
                page_size=0)
        # self.freq_left.connect("value_changed", self.on_freq_left)

        self.lfo_freq_right = Gtk.Adjustment(
                value=1,
                lower=0,
                upper=10,
                step_increment=0.1,
                page_increment=1,
                page_size=0)

        self.min_level_left = Gtk.Adjustment(
                value=0,
                lower=0,
                upper=1,
                step_increment=0.01,
                page_increment=0.1,
                page_size=0)
        # self.min_level_left.connect("value_changed", self.on_power_min)

        self.min_level_right = Gtk.Adjustment(
                value=0,
                lower=0,
                upper=1,
                step_increment=0.01,
                page_increment=0.1,
                page_size=0)

        self.max_level_left = Gtk.Adjustment(
                value=1,
                lower=0,
                upper=1,
                step_increment=0.01,
                page_increment=0.1,
                page_size=0)
        # self.min_level_left.connect("value_changed", self.on_power_min)

        self.max_level_right = Gtk.Adjustment(
                value=1,
                lower=0,
                upper=1,
                step_increment=0.01,
                page_increment=0.1,
                page_size=0)

        self.power_max = Gtk.Adjustment(
                value=100,
                lower=0,
                upper=100,
                step_increment=5,
                page_increment=10,
                page_size=0)
        # self.power_max.connect("value_changed", self.on_power_max)

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
        )

    def build(self) -> ControllerWidget:
        cw = super().build()

        cw.grid.attach(Gtk.Label(label="Left"), 1, 2, 2, 1)
        cw.grid.attach(Gtk.Label(label="Right"), 3, 2, 2, 1)
        cw.grid.attach(Gtk.Label(label="Freq"), 0, 3, 1, 1)
        cw.grid.attach(Gtk.Label(label="LFO"), 0, 4, 1, 1)
        cw.grid.attach(Gtk.Label(label="Min"), 0, 5, 1, 1)

        freq_left = Gtk.SpinButton(
            adjustment=self.freq_left,
            digits=1)
        # power.connect("change-value", self.on_manual_power)
        cw.grid.attach(freq_left, 1, 3, 2, 1)

        freq_right = Gtk.SpinButton(
            adjustment=self.freq_right,
            digits=1)
        # power.connect("change-value", self.on_manual_power)
        cw.grid.attach(freq_right, 3, 3, 2, 1)

        lfo_freq_left = Gtk.SpinButton(
            adjustment=self.lfo_freq_left,
            digits=1)
        # power.connect("change-value", self.on_manual_power)
        cw.grid.attach(lfo_freq_left, 1, 4, 2, 1)

        lfo_freq_right = Gtk.SpinButton(
            adjustment=self.lfo_freq_right,
            digits=1)
        # power.connect("change-value", self.on_manual_power)
        cw.grid.attach(lfo_freq_right, 3, 4, 2, 1)

        min_level_left = Gtk.SpinButton(
            adjustment=self.min_level_left,
            digits=2)
        # power.connect("change-value", self.on_manual_power)
        cw.grid.attach(min_level_left, 1, 5, 2, 1)

        min_level_right = Gtk.SpinButton(
            adjustment=self.min_level_right,
            digits=2)
        # power.connect("change-value", self.on_manual_power)
        cw.grid.attach(min_level_right, 3, 5, 2, 1)

        # power_max = Gtk.SpinButton()
        # power_max.set_adjustment(self.power_max)
        # cw.grid.attach(power_max, 3, 3, 1, 1)

        pulse = Gtk.Button(label="Apply")
        pulse.connect("clicked", self.on_apply)
        cw.grid.attach(pulse, 0, 6, 1, 1)

        return cw
