from __future__ import annotations

from typing import Type

import jack
import numpy

from pyeep.midisynth import SineWave
from pyeep.component.aio import AIOComponent
from pyeep.component.base import export
from pyeep.component.jack import JackComponent
from pyeep.messages import Message, Shutdown

from ..output import Output, PowerOutput, PowerOutputController


class Pattern:
    def __init__(self):
        pass

    def set_rate(self, rate: int):
        pass

    def make_envelopes(self, frames: int) -> tuple[numpy.ndarray, numpy.ndarray]:
        # TODO: pattern generation for envelopes
        dummy = numpy.full(frames, 0.5, dtype=numpy.float64)
        return dummy, dummy


class PatternPlayer(Output, JackComponent, AIOComponent):
    def __init__(self, frequency: float = 440.0, **kwargs):
        super().__init__(rate=0, **kwargs)
        self.sine_left: SineWave
        self.sine_right: SineWave
        self.frequency = frequency
        self.pattern: Pattern | None = None
        self.set_pattern(Pattern())

    def set_jack_client(self, jack_client: jack.Client):
        super().set_jack_client(jack_client)
        self.rate = jack_client.samplerate
        self.sine_left = SineWave(self.rate)
        self.sine_right = SineWave(self.rate)
        self.outport_l = self.jack_client.outports.register('pattern_L')
        self.outport_r = self.jack_client.outports.register('pattern_R')

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
