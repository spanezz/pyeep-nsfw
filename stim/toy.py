from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Callable

from pyeep.app import Message, Shutdown
import pyeep.aio

import buttplug

log = logging.getLogger(__name__)


class NewDevice(Message):
    def __init__(self, *, dev: buttplug.client.client.Device, **kwargs):
        super().__init__(**kwargs)
        self.dev = dev

    def __str__(self):
        return f"new device: {self.dev.name}"


class ScanRequest(Message):
    def __str__(self):
        return "scan request"


class SetPower(Message):
    def __init__(self, *, actuator: buttplug.client.client.Actuator, power: float, **kwargs):
        super().__init__(**kwargs)
        self.actuator = actuator
        self.power = power


class Toys(pyeep.aio.AIOComponent):
    def __init__(self, client_name: str, iface: str, **kwargs):
        kwargs.setdefault("name", "toys")
        super().__init__(**kwargs)
        self.client = buttplug.Client(client_name, buttplug.ProtocolSpec.v3)
        self.connector = buttplug.WebsocketConnector(iface, logger=self.logger)
        self.devices_seen: set[buttplug.client.client.Device] = set()

    async def run(self):
        scanning = False
        await self.client.connect(self.connector)
        try:
            # Send initially known devices
            for dev in self.client.devices.values():
                self.devices_seen.add(dev)
                self.send(NewDevice(dev=dev))

            while True:
                msg = await self.next_message(timeout=0.2)

                match msg:
                    case Shutdown():
                        break
                    case ScanRequest():
                        await self.client.start_scanning()
                        scanning = True
                    case SetPower():
                        await msg.actuator.command(msg.power)
                    case None:
                        pass

                for dev in self.client.devices.values():
                    if dev not in self.devices_seen:
                        self.devices_seen.add(dev)
                        self.send(NewDevice(dev=dev))
        finally:
            if scanning:
                await self.client.stop_scanning()
            await self.client.disconnect()


class ToyPlayer:
    """
    Keep a timed command queue for toy actuators
    """
    def __init__(self, actuator: buttplug.client.client.Actuator):
        self.actuator = actuator

        # Queue of intensities (from 0 to 1) to be played
        self.pattern_queue: deque[float] = deque()

        # Sample rate of pattern_queue
        self.sample_rate: int = 20

        self.frame_nsecs: int = int(round(1_000_000_000 / self.sample_rate))

        # Callable notified of every command sent to the toy
        self.notify_command: Callable[[str], None] | None = None

        self.shutting_down = False

    def shutdown(self):
        self.shutting_down = True

    async def play_pattern(self):
        last_frame = time.time_ns() / self.frame_nsecs
        old: float = 0.0
        while not self.shutting_down:
            # print(f"tick cq={len(self.command_queue)}", end=" ")
            if self.pattern_queue:
                new = self.pattern_queue.popleft()
                if new != old:
                    # print(new)
                    await self.actuator.command(new)
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


class Toy:
    """
    Abstract interface to a toy
    """
    def __init__(self):
        # Queue of intensities (from 0 to 1) to be played
        self.pattern_queue: deque[float] = deque()

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
                    await self.send_command(new)
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


class MockToy(Toy):
    """
    Mock toy, doing nothing
    """
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        log.info("shutting down...")
        self.shutdown()

    async def start(self):
        self.pattern_queue.clear()

    def print_device_info(self):
        print("mock toy device")

    async def send_command(self, power: float):
        cmd = f"Power:{power:.2f}"
        if self.notify_command:
            self.notify_command(cmd)
        else:
            print(f"mock toy send command {cmd!r}")


class ButtplugToy(Toy):
    """
    Toy controlled via buttplug/intiface engine
    """
    def __init__(self, dev: buttplug.client.client.Device):
        super().__init__()
        self.dev = dev
        self.actuator = 0

    async def send_command(self, power: float):
        if self.notify_command:
            self.notify_command(f"Power:{power:.2f}")
        await self.dev.actuators[0].command(power)
