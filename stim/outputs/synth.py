from __future__ import annotations

import math
from typing import Type

import jack

import pyeep.outputs
from pyeep.component.aio import AIOComponent
from pyeep.component.base import export
from pyeep.component.jack import JackComponent

from ..output import PowerOutput, PowerOutputController


class Synth(PowerOutput, JackComponent, AIOComponent):
    def __init__(self, **kwargs):
        super().__init__(rate=0, **kwargs)
        self.power: float = 0.0
        # Phase accumulation synthesis
        # See https://www.gkbrk.com/wiki/PhaseAccumulator/
        self.phase = 0.0

    def set_jack_client(self, jack_client: jack.Client):
        super().set_jack_client(jack_client)
        self.outport = self.jack_client.outports.register('synth')
        self.rate = jack_client.samplerate

    def jack_process(self, frames: int):
        buf = memoryview(self.outport.get_buffer()).cast('f')

        for i in range(frames):
            if self.power == 0.0:
                buf[i] = 0
            else:
                self.phase += 2.0 * math.pi * 440.0 / self.rate
                buf[i] = math.sin(self.phase) * self.power

        # print("PROCESS", frames, self.power)
        # pass
        # messages: list[mido.Message] = []
        # frame_time = self.jack_client.last_frame_time
        # for offset, indata in self.inport.incoming_midi_events():
        #     msg = mido.parse([ord(b) for b in indata])
        #     msg.time = frame_time + offset
        #     # TODO
        #     messages.append(msg)

        # self.hub.loop.call_soon_threadsafe(self._send_mido_messages, messages)

    def get_output_controller(self) -> Type["pyeep.outputs.base.OutputController"]:
        return PowerOutputController

    @export
    def set_power(self, power: float):
        self.power = power
