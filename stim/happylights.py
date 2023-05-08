from __future__ import annotations

import asyncio
import logging
from typing import Type

from pyeep.app import Message

from . import bluetooth
from .output import ColoredOutputController, Output, OutputController, SetColor

log = logging.getLogger(__name__)

COMMAND_CHARACTERISTIC = '0000ffd9-0000-1000-8000-00805f9b34fb'


class HappyLights(Output, bluetooth.BluetoothComponent):
    def __init__(self, **kwargs):
        kwargs.setdefault("rate", 32)
        super().__init__(**kwargs)
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

    async def run_message(self, msg: Message):
        match msg:
            # case SetPower():
            #     if msg.output == self:
            #         cmd = self.cmd_white(int(round(msg.power * 255)))
            #         self.logger.debug("HappyLights command: %s", " ".join(f"{c:x}" for c in cmd))
            #         await client.write_gatt_char(COMMAND_CHARACTERISTIC, cmd)
            case SetColor():
                if msg.output == self:
                    cmd = self.cmd_color(
                         int(round(msg.color[0] * 255)),
                         int(round(msg.color[1] * 255)),
                         int(round(msg.color[2] * 255)),
                    )
                    self.logger.debug("HappyLights command: %s", " ".join(f"{c:x}" for c in cmd))
                    await self.client.write_gatt_char(COMMAND_CHARACTERISTIC, cmd)
