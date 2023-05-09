from __future__ import annotations

import functools
import inspect
import json
import math
import time
from collections import deque
from pathlib import Path
from typing import Iterator, Type

import bleak
import muselsl.constants
import muselsl.muse
import numpy
import scipy

import pyeep.aio
from pyeep import bluetooth
from pyeep.app import Message, Shutdown
from pyeep.inputs.base import (Input, InputController, InputSetActive,
                               InputSetMode, ModeInfo)
from pyeep.lsl import LSLComponent, LSLSamples


class Muse(muselsl.muse.Muse):
    # muselsl.muse.Muse ported to bleak and asyncio
    # See https://github.com/alexandrebarachant/muse-lsl.git
    #
    # I'm overriding most methods here, although it's handy to still subclass
    # the original Muse to keep some of the backend functions

    def __init__(self, client: bleak.BleakClient):
        self.client = client
        self.callback_eeg = None
        self.callback_telemetry = None
        self.callback_control = None
        self.callback_acc = None
        self.callback_gyro = None
        self.callback_ppg = None
        self.time_func = time.time
        self.last_timestamp = self.time_func()

    async def _write_cmd(self, cmd: list[bytes]):
        """Wrapper to write a command to the Muse device.
        cmd -- list of bytes"""
        await self.client.write_gatt_char(
                0x000e - 1,
                bytearray(cmd),
                False)

    async def _write_cmd_str(self, cmd: str):
        """Wrapper to encode and write a command string to the Muse device.
        cmd -- string to send"""
        await self._write_cmd(
                [len(cmd) + 1, *(ord(char) for char in cmd), ord('\n')])

    async def ask_control(self):
        """Send a message to Muse to ask for the control status.

        Only useful if control is enabled (to receive the answer!)

        The message received is a dict with the following keys:
        "hn": device name
        "sn": serial number
        "ma": MAC address
        "id":
        "bp": battery percentage
        "ts":
        "ps": preset selected
        "rc": return status, if 0 is OK
        """
        await self._write_cmd_str('s')

    async def ask_device_info(self):
        """Send a message to Muse to ask for the device info.

        The message received is a dict with the following keys:
        "ap":
        "sp":
        "tp": firmware type, e.g: "consumer"
        "hw": hardware version?
        "bn": build number?
        "fw": firmware version?
        "bl":
        "pv": protocol version?
        "rc": return status, if 0 is OK
        """
        await self._write_cmd_str('v1')

    async def ask_reset(self):
        """Undocumented command reset for '*1'
        The message received is a singleton with:
        "rc": return status, if 0 is OK
        """
        await self._write_cmd_str('*1')

    async def start(self):
        """Start streaming."""
        self.first_sample = True
        self._init_sample()
        self._init_ppg_sample()
        self.last_tm = 0
        self.last_tm_ppg = 0
        self._init_control()
        await self.resume()

    async def resume(self):
        """Resume streaming, sending 'd' command"""
        await self._write_cmd_str('d')

    async def stop(self):
        """Stop streaming."""
        await self._write_cmd_str('h')

    async def keep_alive(self):
        """Keep streaming, sending 'k' command"""
        await self._write_cmd_str('k')

    async def select_preset(self, preset=21):
        """Set preset for headband configuration

        See details here https://articles.jaredcamins.com/figuring-out-bluetooth-low-energy-part-2-750565329a7d
        For 2016 headband, possible choice are 'p20' and 'p21'.
        Untested but possible values include:
          'p22','p23','p31','p32','p50','p51','p52','p53','p60','p61','p63','pAB','pAD'
        Default is 'p21'."""

        if type(preset) is int:
            preset = str(preset)
        if preset[0] == 'p':
            preset = preset[1:]
        if str(preset) != '21':
            print('Sending command for non-default preset: p' + preset)
        preset = bytes(preset, 'utf-8')
        await self._write_cmd([0x04, 0x70, *preset, 0x0a])

    async def _start_notify(self, uuid, callback):
        @functools.wraps(callback)
        def wrap(gatt_characteristic, data):
            value_handle = gatt_characteristic.handle + 1
            callback(value_handle, data)
        await self.client.start_notify(uuid, wrap)

    async def subscribe_eeg(self, callback_eeg):
        """subscribe to eeg stream."""
        self.callback_eeg = callback_eeg
        await self._start_notify(muselsl.constants.MUSE_GATT_ATTR_TP9, callback=self._handle_eeg)
        await self._start_notify(muselsl.constants.MUSE_GATT_ATTR_AF7, callback=self._handle_eeg)
        await self._start_notify(muselsl.constants.MUSE_GATT_ATTR_AF8, callback=self._handle_eeg)
        await self._start_notify(muselsl.constants.MUSE_GATT_ATTR_TP10, callback=self._handle_eeg)
        await self._start_notify(muselsl.constants.MUSE_GATT_ATTR_RIGHTAUX, callback=self._handle_eeg)

    async def subscribe_control(self, callback_control):
        self.callback_control = callback_control
        await self._start_notify(
            muselsl.constants.MUSE_GATT_ATTR_STREAM_TOGGLE, callback=self._handle_control)

        self._init_control()

    async def subscribe_telemetry(self, callback_telemetry):
        self.callback_telemetry = callback_telemetry
        await self._start_notify(
            muselsl.constants.MUSE_GATT_ATTR_TELEMETRY, callback=self._handle_telemetry)

    async def subscribe_acc(self, callback_acc):
        self.callback_acc = callback_acc
        await self._start_notify(
            muselsl.constants.MUSE_GATT_ATTR_ACCELEROMETER, callback=self._handle_acc)

    async def subscribe_gyro(self, callback_gyro):
        self.callback_gyro = callback_gyro
        await self._start_notify(
            muselsl.constants.MUSE_GATT_ATTR_GYRO, callback=self._handle_gyro)

    async def subscribe_ppg(self, callback_ppg):
        self.callback_ppg = callback_ppg
        try:
            """subscribe to ppg stream."""
            await self._start_notify(
                muselsl.contants.MUSE_GATT_ATTR_PPG1, callback=self._handle_ppg)
            await self._start_notify(
                muselsl.contants.MUSE_GATT_ATTR_PPG2, callback=self._handle_ppg)
            await self._start_notify(
                muselsl.contants.MUSE_GATT_ATTR_PPG3, callback=self._handle_ppg)
        except Exception:
            raise Exception(
                'PPG data is not available on this device. PPG is only available on Muse 2'
            )

    async def _disable_light(self):
        await self._write_cmd_str('L0')


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


class GyroAxis:
    def __init__(self, name: str):
        self.name = name
        self.calibration_path = Path(f".cal_gyro_{name}")
        # sample rate = 52
        # 2 seconds window
        self.window_len = 64
        self.window: deque[float] = deque(maxlen=self.window_len)
        self.hamming = scipy.signal.windows.hamming(self.window_len, sym=False)
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
        if len(self.window) == self.window_len:
            signal = self.hamming * self.window
            powers = abs(scipy.fft.rfft(signal))
            freqs = numpy.fft.fftfreq(len(self.window), 1/52)
            idx = numpy.argmax(powers[:32])
            return freqs[idx], powers[idx]
        else:
            return 0, 0


class ModeHeadMovement(ModeBase):
    """
    Head movement
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.x_axis = GyroAxis("x")
        self.y_axis = GyroAxis("y")
        self.z_axis = GyroAxis("z")

    def on_gyro(self, data: numpy.ndarray, timestamps: list[float]):
        for sample in data[0, :]:
            self.x_axis.add(sample)
        for sample in data[1, :]:
            self.y_axis.add(sample)
        for sample in data[2, :]:
            self.z_axis.add(sample)

        selected = None
        for axis in (self.x_axis, self.y_axis, self.z_axis):
            freq, power = axis.value()
            if selected is None or selected[2] < power:
                selected = (axis.name, freq, power)

        if selected[2] > 500:
            self.muse2.send(
                HeadShaken(axis=selected[0], freq=selected[1], power=10*math.log10(selected[2] ** 2))
            )


class Muse2(Input, bluetooth.BluetoothComponent):
    """
    Monitor a Bluetooth LE heart rate monitor
    """
    MODES = {
        "default": ModeDefault,
        "headpos": ModeHeadPosition,
        "headmov": ModeHeadMovement,
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
            case InputSetMode():
                if msg.input == self:
                    self.set_mode(msg.mode)


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
        self.active = False

    @pyeep.aio.export
    @property
    def is_active(self) -> bool:
        return self.active

    @property
    def description(self) -> str:
        return "Head position"

    async def run(self):
        while True:
            msg = await self.next_message()
            match msg:
                case Shutdown():
                    break
                case InputSetActive():
                    if msg.input == self:
                        self.active = msg.value
                case LSLSamples():
                    if self.active:
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


class HeadMovement(Input, LSLComponent):
    def __init__(self, **kwargs):
        kwargs.setdefault("stream_type", "GYRO")
        kwargs.setdefault("max_samples", 8)
        super().__init__(**kwargs)
        self.x_axis = GyroAxis("x")
        self.y_axis = GyroAxis("y")
        self.z_axis = GyroAxis("z")
        self.active = False

    @pyeep.aio.export
    @property
    def is_active(self) -> bool:
        return self.active

    @property
    def description(self) -> str:
        return "Head movement"

    async def run(self):
        while True:
            msg = await self.next_message()
            match msg:
                case Shutdown():
                    break
                case InputSetActive():
                    if msg.input == self:
                        self.active = msg.value
                case LSLSamples():
                    if self.active:
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

        if selected[2] > 500:
            self.send(
                HeadShaken(axis=selected[0], freq=selected[1], power=10*math.log10(selected[2] ** 2))
            )
