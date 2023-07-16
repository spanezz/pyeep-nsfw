from __future__ import annotations

import math
from typing import Type

import jack
import numpy

from pyeep.component.aio import AIOComponent
from pyeep.component.base import export
from pyeep.component.jack import JackComponent
from pyeep.messages import Message, Shutdown
from pyeep.midisynth import SineWave

from ..output import Output, PowerOutput, PowerOutputController


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
    def __init__(self, freq_left: float, freq_right: float, min_left: float = 0.1, min_right: float = 0.1):
        super().__init__()
        self.freq_left = freq_left
        self.freq_right = freq_right
        self.min_left = min_left
        self.min_right = min_right
        self.lfo_left: SineWave
        self.lfo_right: SineWave

    def set_rate(self, rate: int):
        super().set_rate(rate)
        self.lfo_left = SineWave(self.rate)
        self.lfo_right = SineWave(self.rate)

    def make_envelopes(self, frames: int) -> tuple[numpy.ndarray, numpy.ndarray]:
        lfo_left = numpy.zeros(frames)
        lfo_right = numpy.zeros(frames)
        self.lfo_left.wave(lfo_left, self.freq_left)
        self.lfo_right.wave(lfo_right, self.freq_right)

        left_range = 1 - self.min_left
        left = self.min_left + left_range / 2 + lfo_left * left_range / 2

        right_range = 1 - self.min_right
        right = self.min_right + right_range / 2 + lfo_right * right_range / 2

        return left, right


class PatternPlayer(Output, JackComponent, AIOComponent):
    def __init__(self, frequency: float = 1000.0, **kwargs):
        super().__init__(rate=0, **kwargs)
        self.sine_left: SineWave
        self.sine_right: SineWave
        self.frequency = frequency
        self.pattern: Pattern | None = None

    def set_jack_client(self, jack_client: jack.Client):
        super().set_jack_client(jack_client)
        self.rate = jack_client.samplerate
        self.sine_left = SineWave(self.rate)
        self.sine_right = SineWave(self.rate)
        self.outport_l = self.jack_client.outports.register('pattern_L')
        self.outport_r = self.jack_client.outports.register('pattern_R')
        # self.set_pattern(Pan(freq=3))
        self.set_pattern(Pan2(freq_left=2, freq_right=1, min_right=0.4))

    def set_pattern(self, pattern: Pattern):
        self.pattern = pattern
        self.pattern.set_rate(self.rate)

    def jack_process(self, frames: int) -> None:
        if self.pattern is None:
            return

        envelope_l, envelope_r = self.pattern.make_envelopes(frames)

        array_l = self.outport_l.get_array()
        array_l.fill(0)
        self.sine_left.synth(array_l, self.frequency, envelope_l)

        array_r = self.outport_r.get_array()
        array_r.fill(0)
        self.sine_right.synth(array_r, self.frequency, envelope_r)

    async def run(self) -> None:
        while True:
            msg = await self.next_message()
            match msg:
                case Shutdown():
                    break
                # case MidiMessages():
                #     self.synth.add_messages(
                #             msg.last_frame_time,
                #             msg.messages)
