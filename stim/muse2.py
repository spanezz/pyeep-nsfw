from __future__ import annotations

import json
import math
from collections import deque
from pathlib import Path

import numpy
import scipy

from pyeep.app import Message, Shutdown
from pyeep.lsl import LSLComponent, LSLSamples

from .inputs import Input


class HeadMoved(Message):
    def __init__(self, *, pitch: float, roll: float, **kwargs):
        super().__init__(**kwargs)
        self.pitch = pitch
        self.roll = roll

    def __str__(self):
        return super().__str__() + f"(pitch={self.pitch}, roll={self.roll})"


class HeadShaken(Message):
    def __init__(self, *, axis: str, freq: float, power: float, **kwargs):
        super().__init__(**kwargs)
        self.axis = axis
        self.freq = freq
        self.power = power

    def __str__(self):
        return super().__str__() + f"(axis={self.axis}, freq={self.freq}, power={self.power})"


class HeadPosition(Input, LSLComponent):
    def __init__(self, **kwargs):
        kwargs.setdefault("stream_type", "ACC")
        kwargs.setdefault("max_samples", 8)
        super().__init__(**kwargs)

    @property
    def description(self) -> str:
        return "Head position"

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


class GyroAxis:
    def __init__(self, name: str):
        self.name = name
        self.calibration_path = Path(f".cal_gyro_{name}")
        # sample rate = 52
        # 2 seconds window
        self.window: deque[float] = deque(maxlen=64)
        self.bias_samples: list[float] = []
        self.bias: float | None = None
        if self.calibration_path.exists():
            data = json.loads(self.calibration_path.read_text())
            self.bias = data["bias"]

    def add(self, sample: float):
        if self.bias is None and len(self.bias_samples) < 128:
            self.bias_samples.append(sample)
        else:
            if self.bias is None:
                self.bias = numpy.mean(self.bias_samples)
                self.calibration_path.write_text(json.dumps({"bias": self.bias}))
            self.window.append(sample - self.bias)

    def value(self) -> tuple[float, float]:
        """
        Return frequency and power for the frequency band with the highest
        power, computed on the samples in the window
        """
        if self.window:
            powers = abs(scipy.fft.rfft(self.window))
            freqs = numpy.fft.fftfreq(len(self.window), 1/52)
            idx = numpy.argmax(powers[:32])
            return freqs[idx], powers[idx]
            # print(self.name, freqs[idx])
            # print(self.name, freqs[:10])
            # print(self.name, [int(x) for x in numpy.log10(powers[:10])])
            # print(self.name, len(freqs), len(powers), freqs[idx[0]], powers[idx[0]])
            # return sum(self.window) / len(self.window)
        else:
            return 0


class HeadMovement(Input, LSLComponent):
    def __init__(self, **kwargs):
        kwargs.setdefault("stream_type", "GYRO")
        kwargs.setdefault("max_samples", 8)
        super().__init__(**kwargs)
        self.x_axis = GyroAxis("x")
        self.y_axis = GyroAxis("y")
        self.z_axis = GyroAxis("z")

    @property
    def description(self) -> str:
        return "Head movement"

    async def run(self):
        while True:
            msg = await self.next_message()
            match msg:
                case Shutdown():
                    break
                case LSLSamples():
                    await self.process_samples(msg.samples, msg.timestamps)

    async def process_samples(self, samples: list, timestamps: list):
        for x, y, z in samples:
            self.x_axis.add(x)
            self.y_axis.add(y)
            self.z_axis.add(z)

        selected = None
        for axis in (self.x_axis, self.y_axis, self.z_axis):
            freq, power = axis.value()
            if selected is None or selected[2] < power:
                selected = (axis.name, freq, power)

        if selected[2] > 2000:
            self.send(
                HeadShaken(axis=selected[0], freq=selected[1], power=10*math.log10(selected[2] ** 2))
            )
