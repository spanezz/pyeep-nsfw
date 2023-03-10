from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
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
    Send commands to a Lovense device
    """
    def __init__(
            self,
            addr: str,
            read_uuid: str,
            write_uuid: str):
        self.addr = addr
        self.read_uuid = read_uuid
        self.write_uuid = write_uuid
        self.device: BLEDevice
        self.client: BleakClient
        # Queue of commands sent to the device and awaiting a reply
        self.command_queue: deque[LovenseCommand] = deque()
        # Queue of intensities to be played
        self.pattern_queue: deque[int] = deque()
        # Sample rate of pattern_queue
        self.sample_rate: int = 20
        self.frame_nsecs: int = int(round(1_000_000_000 / self.sample_rate))
        self.shutting_down = False
        self.notify_command: Callable[[str], None] | None = None

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
        await self.stop()
        await self.client.__aexit__(exc_type, exc, tb)

    async def start(self):
        await self.client.start_notify(self.read_uuid, self.on_reply)

    async def stop(self):
        self.shutting_down = True

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
        self.shutting_down = True
