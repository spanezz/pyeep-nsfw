from __future__ import annotations

import asyncio
import math
import struct
from typing import Type

import bleak

from pyeep import bluetooth
from pyeep.component.base import check_hub, export
from pyeep.component.controller import ControllerWidget
from pyeep.gtk import Gio, GLib, GObject, Gtk

from ..output import PowerOutput, PowerOutputController


class Coyote(PowerOutput, bluetooth.BluetoothComponent):
    """
    Monitor a Bluetooth LE heart rate monitor

    From the specifications at https://github.com/DG-LAB-OPENSOURCE/DG-LAB-OPENSOURCE
    as translated by deepl:

    # Basic Principle
    Coyote has built-in two groups of independent pulse generation modules,
    corresponding to the A and B channels. Each pulse generation module
    consists of two parts: power supply module and waveform control module.
    We control the pulse generator module through the four variables
    S,X,Y,Z in the Bluetooth protocol.

    # Power Supply Module (S)
    S: PWM_AB2 characteristics

    The power module controls the voltage of the pulse, which is the
    intensity of the channel (the number inside the circle in the App
    interface), corresponding to the parameter S in the Bluetooth protocol,
    with a range of [0-2047] (can't exceed 2047). Each point of intensity
    in our APP is an increase of 7 (the actual intensity value set in the
    taser is 7 times the value shown in the APP). When we write different
    values of parameter S into the APP, the channel intensity changes
    immediately and stays.

    # Waveform Control Module (X Y Z)
    X: 5bits of 4-0bit data in PWM_A34 or PWM_B34.
    Y: 10bits of 14-5 bits of data in PWM_A34 or PWM_B34.
    Z: 5bits of data from 19-15 in PWM_A34 or PWM_B34

    The waveform control module controls the regularity of pulse appearance
    and the variation of pulse width. The pattern of pulse appearance and
    the variation of pulse width are saved as built-in waveforms or
    customized waveforms.

    # Pulse Regularity Control
    Coyote's program divides each second into 1000 milliseconds, and in
    each millisecond a pulse can be generated. We use the X,Y parameters in
    the Bluetooth protocol to encode the pulse generation pattern, where X
    means X pulses are sent out continuously for X milliseconds, and Y
    means that after X pulses, X pulses will be sent out again at an
    interval of Y milliseconds and the cycle will be repeated. the range of
    X is [0-31], and the range of Y is [0-1023].

    e.g.
    Parameter [1,9] means 1 pulse will be emitted every 9ms, and the total
    time consumed is 10ms, that is, the pulse frequency is 100hz. parameter
    [5,95] means 5 pulses will be emitted every 95ms, and the total time
    consumed is 100ms, because these 5 pulses are connected together and
    the duration is only 5ms, so the user will only feel the pulse once (5
    in 1), therefore the pulse frequency is 10hz in the user's body
    sensation. Pulse frequency is 10hz

    # Frequency value
    Frequency = X + Y
    True pulse frequency = Frequency / 1000
    This is a characteristic value of the frequency of the X and Y values
    in relation to each other. You can calculate the most suitable X and Y
    values by setting the Frequency value. The range of values is from 10
    to 1000.

    The ratio of X,Y data is kept according to the formula.

    X = ((Frequency / 1000)^ 0.5) * 15
    Y = Frequency - X
    This is the best result.

    If the X:Y ratio is greater than 1:9 (e.g. [8,2]), the overall feeling of the waveform will be weaker.

    # Pulse Width Control

    A pulse consists of two symmetrical positive and negative unipolar
    pulses, and the height (voltage) of the two unipolar pulses is
    determined by the strength of this channel. We control the strength of
    the sensation caused by the pulse by controlling the pulse width. The
    wider the pulse, the stronger the sensation, and conversely the
    narrower the pulse, the weaker the sensation. Rhythmic changes in pulse
    width can create different pulse sensations.

    The pulse width is controlled by the parameter Z, the range of Z is
    [0-31], the actual pulse width is Z5us. i.e. when Z=20, the pulse width
    is 520us=100us.

    Tips: When the pulse width is greater than 100us (Z>20) the pulse is
    more likely to cause tingling.

    # Creating Changing Waveforms

    Since the parameters of the waveform are not fixed, they are constantly
    changing. Therefore, in Coyote's design, each set of [X,Y,Z] parameters
    is only valid for 0.1S. That is to say, whenever you write a set of
    [X,Y,Z] parameters to the device, the device will output the waveform
    corresponding to the parameters for 0.1S and then stop outputting. That
    is to say, if you need the waveform to maintain a frequency of 100hz, a
    width of 100us and continue to output, then you need to send the
    parameters [1,9,20] to the device every 0.1 seconds.

    Tips: You can also change the value of Frequency every 0.1 seconds, and
    use the Frequency formula to generate the X and Y values automatically.

    More examples

    If you want to create a waveform with a faster and faster frequency,
    you can try to send the following data to the device in sequence every
    0.1 second.

    [5,135,20] [5,125,20] [5,115,20] [5,105,20] [5,95,20] [4,86,20]
    [4,76,20] [4,66,20] [3,57,20] [3,47,20] [3,37,20] [2,28,20] [2,18,20]
    [1,14,20 [1,9,20]

    If you wish to create a waveform that constantly switches between two
    frequencies, try sending the following data to the device in sequence
    every 0.1 seconds.

    If you want to create a waveform with a constant frequency, but with a
    "push" feeling, you can try sending the following data to the device in
    sequence every 0.1 second.

    [1,9,4] [1,9,8] [1,9,12] [1,9,16] [1,9,18] [1,9,19] [1,9,20] [1,9,0]
    [1,9,0] [1,9,0] [1,9,0].

    Tips: The human body is slow to feel the frequency change, so if the
    frequency change is too fast, it will not be able to form a sense of
    rhythm. Frequent changes in pulse width can create a variety of
    sensations.
    """
    COYOTE_SERVICE = "955a180b-0fe2-f5aa-a094-84b8d4f3e8ad"
    CONFIG_CHARACTERISTIC = "955a1507-0fe2-f5aa-a094-84b8d4f3e8ad"
    POWER_CHARACTERISTIC = "955a1504-0fe2-f5aa-a094-84b8d4f3e8ad"
    PATTERNA_CHARACTERISTIC = "955a1506-0fe2-f5aa-a094-84b8d4f3e8ad"
    PATTERNB_CHARACTERISTIC = "955a1505-0fe2-f5aa-a094-84b8d4f3e8ad"

    BATTERY_SERVICE = "955a180a-0fe2-f5aa-a094-84b8d4f3e8ad"
    BATTERY_CHARACTERISTIC = "955a1500-0fe2-f5aa-a094-84b8d4f3e8ad"

    def __init__(self, **kwargs):
        super().__init__(rate=10, **kwargs)

        self.ch_config: bleak.BleakGATTCharacteristic | None = None
        self.ch_power: bleak.BleakGATTCharacteristic | None = None
        self.ch_pattern_a: bleak.BleakGATTCharacteristic | None = None
        self.ch_pattern_b: bleak.BleakGATTCharacteristic | None = None
        self.ch_battery: bleak.BleakGATTCharacteristic | None = None

        self.power_step: int | None = None
        self.power_max: int | None = None

        self.device_power_a: int = 0
        self.device_power_b: int = 0
        self.power_a: int = 0
        self.power_b: int = 0

        self.Ax: int = 0
        self.Ay: int = 0
        self.Az: int = 0

        self.Bx: int = 0
        self.By: int = 0
        self.Bz: int = 0

    def get_output_controller(self) -> Type[CoyoteOutputController]:
        return CoyoteOutputController

    def _encode_channel_power(self, power_a: int, power_b: int) -> bytes:
        power_uint = (power_b << 10) + power_a
        return bytes((
            power_uint >> 16, (power_uint >> 8) & 0xff, power_uint & 0xff
        ))

    def _encode_pattern(self, Ax: int, Ay: int, Az: int):
        pattern_uint = Ax + (Ay << 5) + (Az << 15)
        return bytes((
            (pattern_uint >> 16) & 0xff, (pattern_uint >> 8) & 0xff, pattern_uint & 0xff
        ))

    def _parse_channel_power(self, value: bytes) -> tuple[int, int]:
        power_uint = (value[0] << 16) + (value[1] << 8) + value[2]
        power_a = power_uint & 0x3ff
        power_b = (power_uint >> 10) & 0x3ff
        return power_a, power_b

    def _parse_pattern(self, value: bytes) -> tuple[int, int, int]:
        """
        Parse pattern data and return Az, Ay, Ax byte values
        """
        print("PPAT", value)
        # PWM_A34 A channel waveform data 23-20bit(Reserved) 19-15bit(Az) 14-5bit(Ay) 4-0bit(Ax)
        pattern_uint = (value[2] << 16) + (value[1] << 8) + value[0]
        print(f"PPAT UINT {pattern_uint} {pattern_uint:x} {pattern_uint:b}")
        Ax = pattern_uint & 0x1f  # 5 bits
        Ay = (pattern_uint >> 5) & 0x3ff  # 10 bits
        Az = (pattern_uint >> 15) & 0x1f  # 5 bits
        return Ax, Ay, Az

    async def on_connect(self):
        await super().on_connect()
        print("CONNECT")

        service = self.client.services.get_service(self.COYOTE_SERVICE)
        self.ch_config = self.client.services.get_characteristic(self.CONFIG_CHARACTERISTIC)
        self.ch_power = self.client.services.get_characteristic(self.POWER_CHARACTERISTIC)
        self.ch_pattern_a = self.client.services.get_characteristic(self.PATTERNA_CHARACTERISTIC)
        self.ch_pattern_b = self.client.services.get_characteristic(self.PATTERNB_CHARACTERISTIC)

        char1 = await self.client.read_gatt_char(self.ch_config)
        self.power_step, self.power_max = struct.unpack("<BH", char1)
        print("POWER CONFIG", self.power_max, self.power_step)

        # PWM_AB2 AB two-channel intensity 23-22bit(Reserved) 21-11bit(B
        # channel actual intensity) 10-0bit(A channel actual intensity)
        power_bytes = await self.client.read_gatt_char(self.ch_power)
        power_a, power_b = self._parse_channel_power(power_bytes)
        print("CHANNEL POWER", power_a, power_b)

        # Subscribe to power notifications
        await self.client.start_notify(self.ch_power, self.on_power_changed)
        print("SUBSCRIBED TO POWER")

        # Read current patterns
        pattern_a_bytes = await self.client.read_gatt_char(self.ch_pattern_a)
        self.Ax, self.Ay, self.Az = self._parse_pattern(pattern_a_bytes)
        pattern_b_bytes = await self.client.read_gatt_char(self.ch_pattern_b)
        self.Bx, self.By, self.Bz = self._parse_pattern(pattern_a_bytes)
        print("PATTERN B", self._parse_pattern(pattern_b_bytes))

        # Subscribe to battery notifications
        battery_bytes = await self.client.read_gatt_char(self.ch_battery)
        print("BATTERY%", battery_bytes[0])

        await self.client.start_notify(self.ch_battery, self.on_battery_changed)
        print("SUBSCRIBED TO BATTERY")

        # TODO: set up a 100ms timer to drive the waveform

    def on_power_changed(self, characteristic: bleak.backend.characteristic.BleakGATTCharacteristic, data: bytearray):
        print("OPC")
        self.device_power_a, self.device_power_b = self._parse_channel_power(data)
        print("POWER UPDATE", self.device_power_a, self.device_power_b)

    def on_battery_changed(self, characteristic: bleak.backend.characteristic.BleakGATTCharacteristic, data: bytearray):
        print("OBC")

        print("BATTERY UPDATE", data[0])

    async def _timer_task(self):
        while True:
            # print(round(time.time() - start_time, 1), "Starting periodic function")
            await asyncio.gather(
                asyncio.sleep(0.1),
                self._on_timer(),
            )

    async def _on_timer(self):
        print("TIMER")

        if self.device_power_a == self.power_a and self.device_power_b == self.power_b:
            return

        await self.client.write_gatt_char(self.ch_pattern_a, self._encode_pattern(self.Ax, self.Ay, self.Az))
        await self.client.write_gatt_char(self.ch_pattern_b, self._encode_pattern(self.Bx, self.By, self.Bz))

        coyote_power_a = self.power_max * self.power_a
        coyote_power_b = self.power_max * self.power_b
        coyote_power_a = math.ceil(coyote_power_a / self.power_step) * self.power_step
        coyote_power_b = math.ceil(coyote_power_b / self.power_step) * self.power_step
        print("normalised", coyote_power_a, coyote_power_b)
        encoded = self._encode_channel_power(coyote_power_a, coyote_power_b)
        print("encoded", encoded)

        await self.client.write_gatt_char(self.ch_power, encoded)

    async def run_start(self):
        await super().run_start()
        asyncio.create_task(self._timer_task())

    @export
    def set_power(self, power: float):
        if self.power_max is None:
            return

        print("set power", power)

        self.power_a = power
        self.power_b = power

        # const timer = window.setInterval(()=> {
        #     const ax = parseInt(document.querySelector('#ax').value);
        #     const ay = parseInt(document.querySelector('#ay').value);
        #     const az = parseInt(document.querySelector('#az').value);
        #     patternA.writeValue(encodePattern(ax, ay, az));
        #     const bx = parseInt(document.querySelector('#bx').value);
        #     const by = parseInt(document.querySelector('#by').value);
        #     const bz = parseInt(document.querySelector('#bz').value);
        #     patternB.writeValue(encodePattern(bx, by, bz));

        #     const selectedPowerA = parseInt(powerLevelAInput.value);
        #     const selectedPowerB = parseInt(powerLevelBInput.value);
        #     if (selectedPowerA !== devicePowerA || selectedPowerB !== devicePowerB) {
        #         power.writeValue(encodePower(selectedPowerA, selectedPowerB));
        #         log(`> Writing Power with with: a:${selectedPowerA} ${selectedPowerB}`);
        #     }
        # }, 100);

        # const stopClickListener = stopButton.addEventListener('click', () => {
        #     stopButton.removeEventListener('click', stopClickListener);
        #     clearInterval(timer);
        #     power.writeValue(encodePower(0,0));
        #     powerLevelAInput.value = 0;
        #     powerLevelBInput.value = 0;
        #     startButton.disabled = false;
        #     stopButton.disabled = true;
        # });
        # stopButton.disabled = false;

    # def list_modes(self) -> Iterator[ModeInfo, None]:
    #     """
    #     List available modes
    #     """
    #     for name, value in self.MODES.items():
    #         yield ModeInfo(name, inspect.getdoc(value))

    # @export
    # def set_mode(self, name: str) -> None:
    #     """
    #     Set the active mode
    #     """
    #     self.mode = self.MODES[name](muse2=self)

    # TODO: send keep_alive messages every once in a while


class CoyoteOutputController(PowerOutputController):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def build(self) -> ControllerWidget:
        cw = super().build()

        return cw
