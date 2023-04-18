from __future__ import annotations

import math

import numpy

from pyeep.app import Shutdown, Message
from pyeep.lsl import LSLComponent, LSLSamples


class HeadMoved(Message):
    def __init__(self, *, pitch: float, roll: float, **kwargs):
        super().__init__(**kwargs)
        self.pitch = pitch
        self.roll = roll

    def __str__(self):
        return super().__str__() + f"(pitch={self.pitch}, roll={self.roll})"


class HeadMovement(LSLComponent):
    def __init__(self, **kwargs):
        kwargs.setdefault("name", "head_movement")
        kwargs.setdefault("stream_type", "ACC")
        kwargs.setdefault("max_samples", 8)
        super().__init__(**kwargs)

    async def run(self):
        while True:
            msg = await self.next_message()
            match msg:
                case Shutdown():
                    break
                case LSLSamples():
                    await self.process_samples(msg.samples, msg.timestamps)

    async def process_samples(self, samples: list, timestamps: list):
        data = numpy.array(samples, dtype=float)

        # TODO: replace with a low-pass filter?
        x = numpy.mean(data[:, 0])
        y = numpy.mean(data[:, 1])
        z = numpy.mean(data[:, 2])

        roll = math.atan2(y, z) / math.pi * 180
        pitch = math.atan2(-x, math.sqrt(y*y + z*z)) / math.pi * 180

        self.send(HeadMoved(pitch=pitch, roll=roll))
