from __future__ import annotations

import inspect
import json
import math
from collections import deque
from pathlib import Path
from typing import Iterator, Type

import numpy
import scipy

from pyeep import bluetooth
from pyeep.app import Message, export
from pyeep.app.component import ModeInfo
from pyeep.inputs.base import Input, InputController, InputSetActive
from pyeep.inputs.muse2.aio_muse import Muse


class HeadShaken(Message):
    def __init__(self, *, axis: str, freq: float, power: float, **kwargs):
        super().__init__(**kwargs)
        self.axis = axis
        self.freq = freq
        self.power = power

    def __str__(self):
        return super().__str__() + f"(axis={self.axis}, freq={self.freq}, power={self.power})"


class HeadTurn(Message):
    def __init__(self, *, frames: int, x: float, y: float, z: float, **kwargs):
        super().__init__(**kwargs)
        self.frames = frames
        self.x = x
        self.y = y
        self.z = z

    def __str__(self):
        return super().__str__() + f"(frames={self.frames}, x={self.x}, y={self.y}, z={self.z})"


class ModeBase:
    """
    Base class for Muse2 data processing modes
    """
    def __init__(self, *, muse2: "Muse2"):
        self.muse2 = muse2

    def on_gyro(self, data: numpy.ndarray, timestamps: list[float]):
        pass

    def on_acc(self, data: numpy.ndarray, timestamps: list[float]):
        pass

    def on_eeg(self, data: numpy.ndarray, timestamps: list[float]):
        pass


class ModeDefault(ModeBase):
    """
    Dump to stdout
    """
    def on_gyro(self, data: numpy.ndarray, timestamps: list[float]):
        print("GYRO", data.shape, len(timestamps))

    def on_acc(self, data: numpy.ndarray, timestamps: list[float]):
        print("ACC", data.shape, len(timestamps))

    def on_eeg(self, data: numpy.ndarray, timestamps: list[float]):
        print("EEG", data.shape, len(timestamps))


class ModeHeadPosition(ModeBase):
    """
    Head position
    """
    def on_acc(self, data: numpy.ndarray, timestamps: list[float]):
        # TODO: replace with a low-pass filter
        x = numpy.mean(data[0, :])
        y = numpy.mean(data[1, :])
        z = numpy.mean(data[2, :])

        roll = math.atan2(y, z) / math.pi * 180
        pitch = math.atan2(-x, math.sqrt(y*y + z*z)) / math.pi * 180

        self.muse2.send(HeadMoved(pitch=pitch, roll=roll))


class GyroAxisBase:
    def __init__(self, name: str):
        self.name = name
        self.calibration_path = Path(f".cal_gyro_{name}")
        self.bias_samples: list[float] = []
        self.bias: float | None = None
        if self.calibration_path.exists():
            data = json.loads(self.calibration_path.read_text())
            self.bias = data["bias"]

    def add(self, timestamp: float, sample: float):
        if self.bias is None and len(self.bias_samples) < 256:
            self.bias_samples.append(sample)
        else:
            if self.bias is None:
                self.bias = numpy.mean(self.bias_samples)
                self.calibration_path.write_text(json.dumps({"bias": self.bias}))
            self.process_sample(timestamp, sample)

    def add_samples(self, timestamps: list[float], samples: numpy.ndarray):
        for ts, sample in zip(timestamps, samples):
            self.add(ts, sample - self.bias)


class GyroAxisFFT(GyroAxisBase):
    def __init__(self, name: str):
        super().__init__(name)
        # sample rate = 52
        self.window_len = 64
        self.window: deque[float] = deque(maxlen=self.window_len)
        self.hamming = scipy.signal.windows.hamming(self.window_len, sym=False)

    def process_sample(self, timestamp: float, sample: float):
        self.window.append(sample - self.bias)

    def value(self) -> tuple[float, float]:
        """
        Return frequency and power for the frequency band with the highest
        power, computed on the samples in the window
        """
        if len(self.window) == self.window_len:
            signal = self.hamming * self.window
            powers = abs(scipy.fft.rfft(signal))
            freqs = numpy.fft.fftfreq(len(self.window), 1/52)
            idx = numpy.argmax(powers[:32])
            return freqs[idx], powers[idx]
        else:
            return 0, 0


class GyroAxisLast(GyroAxisBase):
    def __init__(self, name: str):
        super().__init__(name)
        self.last: float = 0

    def process_sample(self, timestamp: float, sample: float):
        self.last = sample

    def value(self) -> float:
        """
        Return the angular velocity along this axis
        """
        return self.last


class ModeHeadGestures(ModeBase):
    """
    Head gestures
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.x_axis = GyroAxisFFT("x")
        self.y_axis = GyroAxisFFT("y")
        self.z_axis = GyroAxisFFT("z")

    def on_gyro(self, data: numpy.ndarray, timestamps: list[float]):
        self.x_axis.add_samples(timestamps, data[0, :])
        self.y_axis.add_samples(timestamps, data[1, :])
        self.z_axis.add_samples(timestamps, data[2, :])

        selected = None
        for axis in (self.x_axis, self.y_axis, self.z_axis):
            freq, power = axis.value()
            if selected is None or selected[2] < power:
                selected = (axis.name, freq, power)

        if selected[2] > 500:
            self.muse2.send(
                HeadShaken(axis=selected[0], freq=selected[1], power=10*math.log10(selected[2] ** 2))
            )


class ModeHeadTurn(ModeBase):
    """
    Head turn
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.rate = 52

        self.x_axis = GyroAxisLast("x")
        self.y_axis = GyroAxisLast("y")
        self.z_axis = GyroAxisLast("z")

    def on_gyro(self, data: numpy.ndarray, timestamps: list[float]):
        self.x_axis.add_samples(timestamps, data[0, :])
        self.y_axis.add_samples(timestamps, data[1, :])
        self.z_axis.add_samples(timestamps, data[2, :])

        x = self.x_axis.value()
        y = self.y_axis.value()
        z = self.z_axis.value()

        self.muse2.send(
            HeadTurn(
                frames=len(timestamps),
                x=round(x),
                y=round(y),
                z=round(z))
        )


class Muse2(Input, bluetooth.BluetoothComponent):
    """
    Monitor a Bluetooth LE heart rate monitor
    """
    MODES = {
        "default": ModeDefault,
        "headpos": ModeHeadPosition,
        "headgest": ModeHeadGestures,
        "headturn": ModeHeadTurn,
    }

    # This has been tested with a Moofit HW401
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.active = False
        self.muse = Muse(self.client)

    def get_input_controller(self) -> Type["InputController"]:
        return InputController

    @property
    def is_active(self) -> bool:
        return self.active

    async def on_connect(self):
        await super().on_connect()
        await self.muse.subscribe_gyro(self.on_gyro)
        await self.muse.subscribe_acc(self.on_acc)
        # await self.muse.subscribe_eeg(self.on_eeg)
        await self.muse.start()

    def on_gyro(self, data: numpy.ndarray, timestamps: list[float]):
        if not self.active:
            return
        self.mode.on_gyro(data, timestamps)

    def on_acc(self, data: numpy.ndarray, timestamps: list[float]):
        if not self.active:
            return
        self.mode.on_acc(data, timestamps)

    def on_eeg(self, data: numpy.ndarray, timestamps: list[float]):
        if not self.active:
            return
        self.mode.on_eeg(data, timestamps)

    def list_modes(self) -> Iterator[ModeInfo, None]:
        """
        List available modes
        """
        for name, value in self.MODES.items():
            yield ModeInfo(name, inspect.getdoc(value))

    @export
    def set_mode(self, name: str) -> None:
        """
        Set the active mode
        """
        self.mode = self.MODES[name](muse2=self)

    # TODO: send keep_alive messages every once in a while

    async def run_message(self, msg: Message):
        match msg:
            case InputSetActive():
                if msg.input == self:
                    self.active = msg.value


class HeadMoved(Message):
    def __init__(self, *, pitch: float, roll: float, **kwargs):
        super().__init__(**kwargs)
        self.pitch = pitch
        self.roll = roll

    def __str__(self):
        return super().__str__() + f"(pitch={self.pitch}, roll={self.roll})"


# Old lsl-based components
# from pyeep.lsl import LSLComponent, LSLSamples
#
# class HeadPosition(Input, LSLComponent):
#     def __init__(self, **kwargs):
#         kwargs.setdefault("stream_type", "ACC")
#         kwargs.setdefault("max_samples", 8)
#         super().__init__(**kwargs)
#         self.active = False
#
#     @pyeep.aio.export
#     @property
#     def is_active(self) -> bool:
#         return self.active
#
#     @property
#     def description(self) -> str:
#         return "Head position"
#
#     async def run(self):
#         while True:
#             msg = await self.next_message()
#             match msg:
#                 case Shutdown():
#                     break
#                 case InputSetActive():
#                     if msg.input == self:
#                         self.active = msg.value
#                 case LSLSamples():
#                     if self.active:
#                         await self.process_samples(msg.samples, msg.timestamps)
#
#     async def process_samples(self, samples: list, timestamps: list):
#         data = numpy.array(samples, dtype=float)
#
#         # TODO: replace with a low-pass filter?
#         x = numpy.mean(data[:, 0])
#         y = numpy.mean(data[:, 1])
#         z = numpy.mean(data[:, 2])
#
#         roll = math.atan2(y, z) / math.pi * 180
#         pitch = math.atan2(-x, math.sqrt(y*y + z*z)) / math.pi * 180
#
#         self.send(HeadMoved(pitch=pitch, roll=roll))
#
#
# class HeadMovement(Input, LSLComponent):
#     def __init__(self, **kwargs):
#         kwargs.setdefault("stream_type", "GYRO")
#         kwargs.setdefault("max_samples", 8)
#         super().__init__(**kwargs)
#         self.x_axis = GyroAxis("x")
#         self.y_axis = GyroAxis("y")
#         self.z_axis = GyroAxis("z")
#         self.active = False
#
#     @pyeep.aio.export
#     @property
#     def is_active(self) -> bool:
#         return self.active
#
#     @property
#     def description(self) -> str:
#         return "Head movement"
#
#     async def run(self):
#         while True:
#             msg = await self.next_message()
#             match msg:
#                 case Shutdown():
#                     break
#                 case InputSetActive():
#                     if msg.input == self:
#                         self.active = msg.value
#                 case LSLSamples():
#                     if self.active:
#                         await self.process_samples(msg.samples, msg.timestamps)
#
#     async def process_samples(self, samples: list, timestamps: list):
#         for x, y, z in samples:
#             self.x_axis.add(x)
#             self.y_axis.add(y)
#             self.z_axis.add(z)
#
#         selected = None
#         for axis in (self.x_axis, self.y_axis, self.z_axis):
#             freq, power = axis.fft_value()
#             if selected is None or selected[2] < power:
#                 selected = (axis.name, freq, power)
#
#         if selected[2] > 500:
#             self.send(
#                 HeadShaken(axis=selected[0], freq=selected[1], power=10*math.log10(selected[2] ** 2))
#             )
