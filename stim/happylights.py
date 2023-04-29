from __future__ import annotations

import asyncio
import logging

import bleak

import pyeep.aio
from pyeep.app import Component, Message, Shutdown
from pyeep.gtk import Gio, GLib

from .output import NewOutput, Output, SetPower

log = logging.getLogger(__name__)

COMMAND_CHARACTERISTIC = '0000ffd9-0000-1000-8000-00805f9b34fb'

# class ScanRequest(Message):
#     def __init__(self, *, scan: bool = True, **kwargs):
#         super().__init__(**kwargs)
#         self.scan = scan
#
#     def __str__(self):
#         return "scan request"


class ColorComponent(Output, pyeep.aio.AIOComponent):
    """
    Control one color component
    """
    def __init__(self, *, lights: "HappyLights", **kwargs):
        kwargs.setdefault("rate", 256)
        super().__init__(**kwargs)
        self.lights = lights
        self.value: int = 0

    async def run(self):
        while True:
            msg = await self.next_message()
            match msg:
                case Shutdown():
                    break
                case SetPower():
                    if msg.output == self:
                        self.value = int(round(msg.power * 255))
                        await self.lights.update()


class HappyLights(pyeep.aio.AIOComponent):
    def __init__(self, address: str, **kwargs):
        super().__init__(**kwargs)
        self.address = address
        self.client: bleak.BleakClient | None = None
        self.red: ColorComponent | None = None
        self.green: ColorComponent | None = None
        self.blue: ColorComponent | None = None
        self.update_event = asyncio.Event()

    @staticmethod
    def cmd_color(r: int, g: int, b: int) -> bytes:
        return bytes([0x56, r, g, b, 00, 0xf0, 0xaa])

    @staticmethod
    def cmd_white(intensity: int) -> bytes:
        return bytes([0x56, 0, 0, 0, intensity, 0x0f, 0xaa])

    @staticmethod
    def cmd_on() -> bytes:
        return bytes([0xcc, 0x23, 0x33])

    @staticmethod
    def cmd_off() -> bytes:
        return bytes([0xcc, 0x24, 0x33])

    async def update(self):
        self.update_event.set()

    async def lights_task(self):
        # device = await bleak.BleakScanner.find_device_by_address(self.address)
        # if device is None:
        #     self.logger.error("%s: happy ligths not found", self.address)

        # async with bleak.BleakClient(device) as client:
        async with bleak.BleakClient(self.address) as client:
            self.client = client
            self.red = self.hub.app.add_component(ColorComponent, name="happylights-red", lights=self)
            self.green = self.hub.app.add_component(ColorComponent, name="happylights-green", lights=self)
            self.blue = self.hub.app.add_component(ColorComponent, name="happylights-blue", lights=self)
            self.send(NewOutput(output=self.red))
            self.send(NewOutput(output=self.green))
            self.send(NewOutput(output=self.blue))
            while True:
                await self.update_event.wait()
                self.update_event.clear()
                cmd = self.cmd_color(self.red.value, self.green.value, self.blue.value)
                self.logger.debug("HappyLights command: %s", " ".join(f"{c:x}" for c in cmd))
                await client.write_gatt_char(COMMAND_CHARACTERISTIC, cmd)

    async def run(self):
        async with asyncio.TaskGroup() as tg:
            lights = tg.create_task(self.lights_task())

            try:
                while True:
                    match await self.next_message():
                        case Shutdown():
                            break
            finally:
                lights.cancel()

