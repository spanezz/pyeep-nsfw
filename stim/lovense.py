from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from pathlib import Path
from typing import Callable

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice

log = logging.getLogger(__name__)


class LovenseCommand:
    def __init__(self, cmd: str):
        self.cmd = cmd
        self.response: str | None = None


class Lovense:
    """
    Abstract interface to a Lovense toy
    """
    def __init__(self, conf: Path):
        with open(conf, "rt") as fd:
            data = json.load(fd)

        self.addr = data["mac"]
        self.read_uuid = data["read_uuid"]
        self.write_uuid = data["write_uuid"]

        # Queue of commands sent to the device and awaiting a reply
        self.command_queue: deque[LovenseCommand] = deque()

        # Queue of intensities to be played
        self.pattern_queue: deque[int] = deque()

        # Sample rate of pattern_queue
        self.sample_rate: int = 20

        self.frame_nsecs: int = int(round(1_000_000_000 / self.sample_rate))

        self.shutting_down = False

        # Callable notified of every command sent to the toy
        self.notify_command: Callable[[str], None] | None = None

    def shutdown(self):
        self.shutting_down = True

    async def play_pattern(self):
        last_frame = time.time_ns() / self.frame_nsecs
        old: int = 0
        while not self.shutting_down:
            # print(f"tick cq={len(self.command_queue)}", end=" ")
            if self.pattern_queue:
                new = self.pattern_queue.popleft()
                if new != old:
                    # print(new)
                    await self.send_command(f"Vibrate:{new};")
                    old = new
                else:
                    # print("same")
                    pass
            else:
                # print("empty")
                pass

            last_frame += 1
            target_time = last_frame * self.frame_nsecs
            cur_time = time.time_ns()
            if target_time > cur_time:
                await asyncio.sleep((target_time - cur_time) / 1_000_000_000)


class RealLovense(Lovense):
    """
    Send commands to a Lovense device
    """
    def __init__(self, conf: Path):
        super().__init__(conf)
        self.device: BLEDevice
        self.client: BleakClient

    async def __aenter__(self):
        log.info("looking for device...")
        device = await BleakScanner.find_device_by_address(self.addr)
        if device is None:
            raise RuntimeError(f"could not find device with address {self.addr}")
        self.device = device

        log.info("connecting to device...")
        self.client = BleakClient(
            self.device,
            disconnected_callback=self.on_disconnect,
        )
        await self.client.__aenter__()
        log.info("Connected")

        return self

    async def __aexit__(self, exc_type, exc, tb):
        log.info("shutting down...")
        self.shutdown()
        return await self.client.__aexit__(exc_type, exc, tb)

    async def start(self):
        await self.client.start_notify(self.read_uuid, self.on_reply)
        self.pattern_queue.clear()

    def print_device_info(self):
        for service in self.client.services:
            print(f"service {service.uuid}")
            for c in service.characteristics:
                print(f"  characteristic {c.uuid} {c.description} {c.handle} ({len(c.descriptors)} descriptors)")

    async def send_command(self, cmd: str):
        if self.notify_command:
            self.notify_command(cmd)
        command = LovenseCommand(cmd)
        self.command_queue.append(command)
        await self.client.write_gatt_char(self.write_uuid, cmd.encode())

    def on_reply(self, characteristic: BleakGATTCharacteristic, data: bytearray):
        if self.command_queue:
            cmd = self.command_queue.popleft()
            cmd.response = data
            # FIXME: so far this is only discarded: is there anything we need to do?
            # FIXME: at least check that the response is OK? Let the command
            # process the response and raise if needed?

    def on_disconnect(self, client: BleakClient):
        """
        Called when client disconnects
        """
        self.shutdown()


class MockLovense(Lovense):
    """
    Send commands to a Lovense device
    """
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        log.info("shutting down...")
        self.shutdown()

    async def start(self):
        self.pattern_queue.clear()

    def print_device_info(self):
        print("mock lovense device")

    async def send_command(self, cmd: str):
        if self.notify_command:
            self.notify_command(cmd)
        else:
            print(f"mock lovense send command {cmd!r}")
