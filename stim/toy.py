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
    def __init__(self, *, actuator: "Actuator", **kwargs):
        super().__init__(**kwargs)
        self.actuator = actuator

    def __str__(self):
        return f"new device: {self.actuator.actuator._device.name} {self.actuator.name}"


class ScanRequest(Message):
    def __init__(self, *, scan: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.scan = scan

    def __str__(self):
        return "scan request"


class SetPower(Message):
    def __init__(self, *, actuator: "Actuator", power: float, **kwargs):
        super().__init__(**kwargs)
        self.actuator = actuator
        self.power = power


class Actuator(pyeep.aio.AIOComponent):
    """
    Component driving an actuator
    """
    def __init__(self, *, actuator: buttplug.client.client.Actuator, sample_rate: int = 20, **kwargs):
        super().__init__(**kwargs)
        self.actuator = actuator

        # Queue of intensities (from 0 to 1) to be played
        self.pattern_queue: deque[float] = deque()

        # Sample rate of pattern_queue
        self.sample_rate: int = 20

        self.frame_nsecs: int = int(round(1_000_000_000 / self.sample_rate))

    async def run(self):
        await self.process_messages()

    async def process_messages(self):
        while True:
            msg = await self.next_message()
            match msg:
                case Shutdown():
                    break
                # case ScanRequest():
                #     await self.client.start_scanning()
                #     scanning = True
                case SetPower():
                    if msg.actuator == self:
                        await self.actuator.command(msg.power)

    # async def play_pattern(self):
    #     last_frame = time.time_ns() / self.frame_nsecs
    #     old: int = 0
    #     while not self.shutting_down:
    #         # print(f"tick cq={len(self.command_queue)}", end=" ")
    #         if self.pattern_queue:
    #             new = self.pattern_queue.popleft()
    #             if new != old:
    #                 # print(new)
    #                 await self.send_command(new)
    #                 old = new
    #             else:
    #                 # print("same")
    #                 pass
    #         else:
    #             # print("empty")
    #             pass

    #         last_frame += 1
    #         target_time = last_frame * self.frame_nsecs
    #         cur_time = time.time_ns()
    #         if target_time > cur_time:
    #             await asyncio.sleep((target_time - cur_time) / 1_000_000_000)


class Toys(pyeep.aio.AIOComponent):
    def __init__(self, client_name: str, iface: str, **kwargs):
        kwargs.setdefault("name", "toys")
        super().__init__(**kwargs)
        self.client = buttplug.Client(client_name, buttplug.ProtocolSpec.v3)
        self.connector = buttplug.WebsocketConnector(iface, logger=self.logger)
        self.devices_seen: set[buttplug.client.client.Device] = set()

    def _new_device(self, dev: buttplug.client.client.Device):
        name = f"bp_dev{dev.index}"

        for a in dev.actuators:
            actuator = self.hub.app.add_component(Actuator, name=f"{name}_act{a.index}", actuator=a)
            self.send(NewDevice(actuator=actuator))

        # for a in dev.linear_actuators:
        #     print(f"* Linear actuator {a.description} {a.__class__.__name__}")

        # for a in dev.rotatory_actuators:
        #     print(f"* Rotatory actuator: {a.description} {a.__class__.__name__}")

        # for s in dev.sensors:
        #     value = await s.read()
        #     print(f"* Sensor: {s.description} {s.__class__.__name__}: {value}")

    async def run(self):
        scanning = False
        await self.client.connect(self.connector)
        try:
            # Create components for initially known devices
            for dev in self.client.devices.values():
                self.devices_seen.add(dev)
                self._new_device(dev)

            while True:
                msg = await self.next_message(timeout=0.2)

                match msg:
                    case Shutdown():
                        break
                    case ScanRequest():
                        if msg.scan:
                            await self.client.start_scanning()
                        else:
                            await self.client.stop_scanning()
                        scanning = msg.scan
                    # case SetPower():
                    #     await msg.actuator.command(msg.power)
                    case None:
                        pass

                for dev in self.client.devices.values():
                    if dev not in self.devices_seen:
                        # Create components for newly discovered devices
                        self.devices_seen.add(dev)
                        self._new_device(dev)

        finally:
            if scanning:
                await self.client.stop_scanning()
            await self.client.disconnect()


class ToyPlayer:
    """
    Keep a timed command queue for toy actuators
    """
    def __init__(self, actuator: Actuator, sender: Callable):
        self.actuator = actuator
        self.sender = sender

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
                    self.sender(SetPower(actuator=self.actuator, power=new))
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


# class MockToy(Toy):
#     """
#     Mock toy, doing nothing
#     """
#     async def __aenter__(self):
#         return self
#
#     async def __aexit__(self, exc_type, exc, tb):
#         log.info("shutting down...")
#         self.shutdown()
#
#     async def start(self):
#         self.pattern_queue.clear()
#
#     def print_device_info(self):
#         print("mock toy device")
#
#     async def send_command(self, power: float):
#         cmd = f"Power:{power:.2f}"
#         if self.notify_command:
#             self.notify_command(cmd)
#         else:
#             print(f"mock toy send command {cmd!r}")
#
#
# class ButtplugToy(Toy):
#     """
#     Toy controlled via buttplug/intiface engine
#     """
#     def __init__(self, dev: buttplug.client.client.Device):
#         super().__init__()
#         self.dev = dev
#         self.actuator = 0
#
#     async def send_command(self, power: float):
#         if self.notify_command:
#             self.notify_command(f"Power:{power:.2f}")
#         await self.dev.actuators[0].command(power)
