from __future__ import annotations

import math
from typing import Type

import jack
import numba
import numpy
from numba.experimental import jitclass

import pyeep.outputs
from pyeep import midisynth
from pyeep.component.aio import AIOComponent
from pyeep.component.base import export
from pyeep.component.jack import JackComponent
from pyeep.inputs.midi import MidiMessages
from pyeep.messages import Message, Shutdown

from ..output import Output, PowerOutput, PowerOutputController


class PlayAudio(Message):
    def __init__(self, last_frame_time: int, frames: int, audio: numpy.ndarray, **kwargs):
        super().__init__(**kwargs)
        self.last_frame_time = last_frame_time
        self.frames = frames
        self.audio = audio

    def __str__(self) -> str:
        return super().__str__() + (
                f"(last_frame_time={self.last_frame_time},"
                f" frames={self.frames},"
                f" audio={len(self.audio)})")


@jitclass([
    ("rate", numba.int32),
    ("phase", numba.float64),
])
class SimpleSynth:
    """
    Phase accumulation synthesis
    """
    # See https://www.gkbrk.com/wiki/PhaseAccumulator/

    def __init__(self, rate: int):
        self.rate: int = rate
        self.phase: float = 0.0

    def synth(self, buf: memoryview, frames: int, freq: float, power: float) -> None:
        for i in range(frames):
            if power == 0.0:
                buf[i] = 0
            else:
                self.phase += 2.0 * math.pi * freq / self.rate
                buf[i] = math.sin(self.phase) * power


class Synth(PowerOutput, JackComponent, AIOComponent):
    def __init__(self, **kwargs):
        super().__init__(rate=0, **kwargs)
        self.power: float = 0.0
        self.synth: SimpleSynth

    def set_jack_client(self, jack_client: jack.Client):
        super().set_jack_client(jack_client)
        self.outport = self.jack_client.outports.register('synth')
        self.rate = jack_client.samplerate
        self.synth = SimpleSynth(self.rate)

    def jack_process(self, frames: int) -> None:
        buf = memoryview(self.outport.get_buffer()).cast('f')
        self.synth.synth(buf, frames, 440.0, self.power)

    def get_output_controller(self) -> Type["pyeep.outputs.base.OutputController"]:
        return PowerOutputController

    @export
    def set_power(self, power: float):
        self.power = power


class Player(Output, JackComponent, AIOComponent):
    def __init__(self, **kwargs):
        super().__init__(rate=0, **kwargs)
        # TODO: jack has a RingBuffer class for this
        self.synth: midisynth.MidiSynth
        self.instruments: midisynth.Instruments

    def set_jack_client(self, jack_client: jack.Client):
        super().set_jack_client(jack_client)
        self.outport = self.jack_client.outports.register('player')
        self.rate = jack_client.samplerate

        self.synth = midisynth.MidiSynth(in_samplerate=self.rate)

        # Set up the synth instrument bank
        self.instruments = midisynth.Instruments(
                midisynth.AudioConfig(
                    in_samplerate=self.rate,
                    out_samplerate=self.rate,
                    dtype=numpy.float32))
        self.instruments.set(0, midisynth.Sine)
        self.instruments.set(1, midisynth.Saw)
        self.synth.add_output(self.instruments)

    def jack_process(self, frames: int) -> None:
        audio = self.instruments.generate(
                    self.jack_client.last_frame_time,
                    frames)

        self.outport.get_array()[:] = audio

    async def run(self) -> None:
        while True:
            msg = await self.next_message()
            match msg:
                case Shutdown():
                    break
                case MidiMessages():
                    self.synth.add_messages(
                            msg.last_frame_time,
                            msg.messages)