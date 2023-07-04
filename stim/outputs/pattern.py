from __future__ import annotations

from typing import Type

import jack
import numpy

from pyeep.midisynth import SineWave, SawWave
from pyeep.component.aio import AIOComponent
from pyeep.component.base import export
from pyeep.component.jack import JackComponent
from pyeep.messages import Message, Shutdown

from ..output import Output, PowerOutput, PowerOutputController


class PatternPlayer(Output, JackComponent, AIOComponent):
    def __init__(self, frequency: float = 440.0, **kwargs):
        super().__init__(rate=0, **kwargs)
        self.sine_left: SineWave
        self.sine_right: SineWave
        self.frequency = frequency

    def set_jack_client(self, jack_client: jack.Client):
        super().set_jack_client(jack_client)
        self.rate = jack_client.samplerate
        self.sine_left = SineWave(self.rate)
        self.sine_right = SineWave(self.rate)
        self.outport_l = self.jack_client.outports.register('pattern_L')
        self.outport_r = self.jack_client.outports.register('pattern_R')

    def jack_process(self, frames: int) -> None:
        # TODO: pattern generation for envelope
        envelope = numpy.full(frames, 0.5, dtype=numpy.float64)
        array_l = self.outport_l.get_array()
        array_l.fill(0)
        self.sine_left.synth(array_l, self.frequency, envelope)
        array_r = self.outport_r.get_array()
        array_r.fill(0)
        self.sine_right.synth(array_r, self.frequency, envelope)

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
