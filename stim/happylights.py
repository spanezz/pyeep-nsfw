from __future__ import annotations

import asyncio
import logging
from typing import Type

import bleak

import pyeep.aio
from pyeep.app import Shutdown

from .output import (ColoredOutputController, Output, OutputController,
                     SetColor, SetPower)

log = logging.getLogger(__name__)

COMMAND_CHARACTERISTIC = '0000ffd9-0000-1000-8000-00805f9b34fb'


class HappyLights(Output, pyeep.aio.AIOComponent):
    def __init__(self, address: str, **kwargs):
        kwargs.setdefault("rate", 256)
        super().__init__(**kwargs)
        self.address = address
        self.client: bleak.BleakClient | None = None
        self.red: int = 0
        self.green: int = 0
        self.blue: int = 0
        self.update_event = asyncio.Event()

    def get_output_controller(self) -> Type["OutputController"]:
        return ColoredOutputController

    @staticmethod
    def cmd_color(r: int, g: int, b: int) -> bytes:
        return bytes([0x56, r, g, b, 0x00, 0xf0, 0xaa])

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

    async def run(self):
        # device = await bleak.BleakScanner.find_device_by_address(self.address)
        # if device is None:
        #     self.logger.error("%s: happy ligths not found", self.address)
        # async with bleak.BleakClient(device) as client:

        async with bleak.BleakClient(self.address) as client:
            while True:
                match (msg := await self.next_message()):
                    case Shutdown():
                        break
                    case SetPower():
                        if msg.output == self:
                            cmd = self.cmd_white(int(round(msg.power * 255)))
                            self.logger.debug("HappyLights command: %s", " ".join(f"{c:x}" for c in cmd))
                            await client.write_gatt_char(COMMAND_CHARACTERISTIC, cmd)
                    case SetColor():
                        if msg.output == self:
                            cmd = self.cmd_color(
                                 int(round(msg.color[0] * 255)),
                                 int(round(msg.color[1] * 255)),
                                 int(round(msg.color[2] * 255)),
                            )
                            self.logger.debug("HappyLights command: %s", " ".join(f"{c:x}" for c in cmd))
                            await client.write_gatt_char(COMMAND_CHARACTERISTIC, cmd)
