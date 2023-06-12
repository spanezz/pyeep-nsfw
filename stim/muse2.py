from __future__ import annotations

import inspect
import json
import math
from pathlib import Path
from typing import Iterator, Type

import numpy

from pyeep import bluetooth
from pyeep.component.active import SimpleActiveComponent
from pyeep.component.modes import ModeInfo
from pyeep.component.controller import ControllerWidget
from pyeep.component.base import export
from pyeep.gtk import Gtk
from pyeep.inputs.base import Input, InputController
from pyeep.inputs.muse2.aio_muse import Muse
from pyeep.messages import Message

from . import dsp


class HeadYesNo(Message):
    def __init__(self, *, frames: int, gesture: str, delay: float, intensity: float, **kwargs):
        super().__init__(**kwargs)
        self.frames = frames
        self.gesture = gesture
        self.delay = delay
        self.intensity = intensity

    def __str__(self):
        return super().__str__() + (
            f"(frames={self.frames}, gesture={self.gesture}, delay={self.delay}, intensity={self.intensity})"
        )


class HeadMoved(Message):
    def __init__(self, *, frames: int, pitch: float, roll: float, **kwargs):
        super().__init__(**kwargs)
        self.frames = frames
        self.pitch = pitch
        self.roll = roll

    def __str__(self):
        return super().__str__() + f"(frames={self.frames}, pitch={self.pitch}, roll={self.roll})"

    def _distance2(self) -> float:
        """
        Experiment with comparing messages
        """
        return self.pitch ** 2 + self.roll ** 2


class HeadGyro(Message):
    def __init__(
            self, *,
            timestamps: numpy.ndarray,
            x: numpy.ndarray,
            y: numpy.ndarray,
            z: numpy.ndarray,
            **kwargs):
        super().__init__(**kwargs)
        self.timestamps = timestamps
        self.x = x
        self.y = y
        self.z = z

    def __str__(self):
        return super().__str__() + (
            f"(timestamps={self.timestamps},"
            f" x={self.x}, y={self.y}, z={self.z})"
        )

    # def _distance2(self) -> float:
    #     """
    #     Experiment with comparing messages
    #     """
    #     return self.x ** 2 + self.y ** 2 + self.z ** 2

    # def _adistance2(self) -> float:
    #     """
    #     Experiment with comparing messages
    #     """
    #     return self.ax ** 2 + self.ay ** 2 + self.az ** 2


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
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.filter_pitch = dsp.Butterworth(rate=52, cutoff=15)
        self.filter_roll = dsp.Butterworth(rate=52, cutoff=15)

    def on_acc(self, data: numpy.ndarray, timestamps: list[float]):
        frames = len(timestamps)
        for i in range(frames):
            x = data[0, i]
            y = data[1, i]
            z = data[2, i]

            roll = math.atan2(y, z) / math.pi * 180
            pitch = math.atan2(-x, math.sqrt(y*y + z*z)) / math.pi * 180

            roll = self.filter_roll(roll)
            pitch = self.filter_pitch(pitch)

        self.muse2.send(HeadMoved(frames=frames, pitch=pitch, roll=roll))


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
            self.process_sample(timestamp, sample - self.bias)

    def add_samples(self, timestamps: list[float], samples: numpy.ndarray):
        for ts, sample in zip(timestamps, samples):
            self.add(ts, sample)


# class GyroAxisFFT(GyroAxisBase):
#     def __init__(self, name: str):
#         super().__init__(name)
#         # sample rate = 52
#         self.window_len = 64
#         self.window: deque[float] = deque(maxlen=self.window_len)
#         self.hamming = scipy.signal.windows.hamming(self.window_len, sym=False)
#
#     def process_sample(self, timestamp: float, sample: float):
#         self.window.append(sample - self.bias)
#
#     def value(self) -> tuple[float, float]:
#         """
#         Return frequency and power for the frequency band with the highest
#         power, computed on the samples in the window
#         """
#         if len(self.window) == self.window_len:
#             signal = self.hamming * self.window
#             powers = abs(scipy.fft.rfft(signal))
#             freqs = numpy.fft.fftfreq(len(self.window), 1/52)
#             idx = numpy.argmax(powers[:32])
#             return freqs[idx], powers[idx]
#         else:
#             return 0, 0


class GyroAxisSwing(GyroAxisBase):
    def __init__(self, name: str, gesture: str, max_dps: float):
        super().__init__(name)
        self.gesture = gesture
        self.max_dps = max_dps
        self.sign: float | None = None
        self.gesture_start: float | None = None
        self.gesture_end: float | None = None
        self.total_angle: float = 0

    def process_sample(self, timestamp: float, sample: float):
        sign = math.copysign(1, sample)
        if self.sign is None or self.sign != sign:
            # Start a new gesture
            self.sign = sign
            self.gesture_start = timestamp
            self.total_angle = 0
        self.total_angle += sample
        self.gesture_end = timestamp

    def value(self) -> tuple[float, float]:
        """
        Return the gesture duration (seconds) and intensity (from 0 to 1) since
        the last direction change
        """
        elapsed = self.gesture_end - self.gesture_start
        dps = abs(self.total_angle / 52 / elapsed)
        return elapsed, numpy.clip(dps / self.max_dps, 0, 1)


class GyroAxisLast(GyroAxisBase):
    def __init__(self, name: str):
        super().__init__(name)
        self.last: float = 0
        self.alast: float = 0

    def process_sample(self, timestamp: float, sample: float):
        self.alast = sample - self.last
        self.last = sample

    def value(self) -> float:
        """
        Return the angular velocity along this axis
        """
        return self.last, self.alast


class ModeHeadYesNo(ModeBase):
    """
    Head yes/no
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.x_axis = GyroAxisSwing("x", "meh", max_dps=200)
        self.y_axis = GyroAxisSwing("y", "yes", max_dps=150)
        self.z_axis = GyroAxisSwing("z", "no", max_dps=200)

    def on_gyro(self, data: numpy.ndarray, timestamps: list[float]):
        self.x_axis.add_samples(timestamps, data[0, :])
        self.y_axis.add_samples(timestamps, data[1, :])
        self.z_axis.add_samples(timestamps, data[2, :])

        selected = None
        for axis in (self.x_axis, self.y_axis, self.z_axis):
            delay, intensity = axis.value()
            if delay < 0.05:
                continue
            if selected is None or selected[2] < intensity:
                selected = (axis.gesture, delay, intensity)

        # if selected[2] > 500:
        if selected is not None:
            self.muse2.send(
                HeadYesNo(frames=len(timestamps), gesture=selected[0], delay=selected[1], intensity=selected[2])
            )


class ModeHeadGyro(ModeBase):
    """
    Head gyro
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.rate = 52

    def on_gyro(self, data: numpy.ndarray, timestamps: list[float]):
        self.muse2.send(
            HeadGyro(
                timestamps=timestamps,
                x=data[0, :],
                y=data[1, :],
                z=data[2, :],
            )
        )


class Muse2(SimpleActiveComponent, Input, bluetooth.BluetoothComponent):
    """
    Monitor a Bluetooth LE heart rate monitor
    """
    MODES = {
        "default": ModeDefault,
        "headpos": ModeHeadPosition,
        "headgest": ModeHeadYesNo,
        "headturn": ModeHeadGyro,
    }

    # This has been tested with a Moofit HW401
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.muse = Muse(self.client)

    def get_controller(self) -> Type["InputController"]:
        return Muse2InputController

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


class Muse2InputController(InputController):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.monitor = Gtk.EntryBuffer()
        self.last_msg_hg: HeadGyro | None = None
        self.last_msg_hga: HeadGyro | None = None
        self.last_msg_mv: HeadMoved | None = None

    def on_reset(self, button):
        self.last_msg_hg = None
        self.last_msg_hga = None
        self.last_msg_mv = None
        self.monitor.set_text("", 0)

    def build(self) -> ControllerWidget:
        cw = super().build()
        monitor = Gtk.Text(buffer=self.monitor)
        cw.grid.attach(monitor, 0, 3, 1, 1)
        reset = Gtk.Button(label="reset")
        reset.connect("clicked", self.on_reset)
        cw.grid.attach(reset, 0, 4, 1, 1)
        return cw

    def receive(self, msg: Message):
        match msg:
            # case HeadGyro():
            #     maxxed = False
            #     if self.last_msg_hg is None or self.last_msg_hg._distance2() < msg._distance2():
            #         self.last_msg_hg = msg
            #         maxxed = True
            #     if self.last_msg_hga is None or self.last_msg_hga._adistance2() < msg._adistance2():
            #         self.last_msg_hga = msg
            #         maxxed = True
            #     if maxxed:
            #         text = ""
            #         if (m := self.last_msg_hg):
            #             text += f"x={m.x:.2f} y={m.y:.2f} z={m.z:.2f}"
            #         if (m := self.last_msg_hga):
            #             if text:
            #                 text += " "
            #             text += f"ax={m.ax:.2f} ay={m.ay:.2f} az={m.az:.2f}"
            #         self.monitor.set_text(text, len(text))

            case HeadMoved():
                if self.last_msg_mv is None or self.last_msg_mv._distance2() < msg._distance2():
                    self.last_msg_mv = msg
                    text = f"pitch={msg.pitch:.1f} roll={msg.roll:.1f}"
                    self.monitor.set_text(text, len(text))


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
