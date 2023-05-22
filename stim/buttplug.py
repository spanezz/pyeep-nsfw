from __future__ import annotations

import asyncio
from typing import Type

import buttplug
import pyeep.aio
import pyeep.outputs
from pyeep.component.aio import AIOComponent
from pyeep.component.base import export
from pyeep.messages import DeviceScanRequest, Message, Shutdown

from .output import PowerOutput, PowerOutputController


class SetPower(Message):
    """
    Internal use only
    """
    def __init__(self, *, power: float, **kwargs):
        super().__init__(**kwargs)
        self.power = power

    def __str__(self) -> str:
        return super().__str__() + f"(power={self.power})"


class Actuator(PowerOutput, AIOComponent):
    """
    Component driving an actuator
    """
    def __init__(self, *, actuator: buttplug.client.client.Actuator, **kwargs):
        kwargs.setdefault("rate", 20)
        super().__init__(**kwargs)
        self.actuator = actuator

    @property
    def description(self) -> str:
        return f"{self.actuator._device.name} {self.name}"

    def get_output_controller(self) -> Type["pyeep.outputs.base.OutputController"]:
        return PowerOutputController

    @export
    def set_power(self, power: float):
        self.receive(SetPower(power=power))

    async def run(self):
        while True:
            msg = await self.next_message()
            match msg:
                case Shutdown():
                    break
                case SetPower():
                    await self.actuator.command(msg.power)


class ButtplugClient(AIOComponent):
    def __init__(self, client_name: str, iface: str, **kwargs):
        kwargs.setdefault("name", "buttplug_client")
        super().__init__(**kwargs)
        self.client = buttplug.Client(client_name, buttplug.ProtocolSpec.v3)
        self.connector = buttplug.WebsocketConnector(iface, logger=self.logger)
        self.devices_seen: set[buttplug.client.client.Device] = set()
        self.scan_task: asyncio.Task | None = None

    def _new_device(self, dev: buttplug.client.client.Device):
        name = f"bp_dev{dev.index}"

        for a in dev.actuators:
            self.hub.app.add_component(Actuator, name=f"{name}_act{a.index}", actuator=a)

        # for a in dev.linear_actuators:
        #     print(f"* Linear actuator {a.description} {a.__class__.__name__}")

        # for a in dev.rotatory_actuators:
        #     print(f"* Rotatory actuator: {a.description} {a.__class__.__name__}")

        # for s in dev.sensors:
        #     value = await s.read()
        #     print(f"* Sensor: {s.description} {s.__class__.__name__}: {value}")

    async def _scan(self, duration: float = 2.0):
        self.logger.info("started scanning")
        await self.client.start_scanning()
        await asyncio.sleep(duration)
        await self.client.stop_scanning()
        self.scan_task = None
        self.logger.info("stopped scanning")

    async def scan(self, duration: float = 2.0):
        if self.scan_task is None:
            self.scan_task = asyncio.create_task(self._scan(duration=duration))

    async def run(self):
        await self.client.connect(self.connector)
        try:
            # Create components for initially known devices
            for dev in self.client.devices.values():
                self.devices_seen.add(dev)
                self._new_device(dev)

            while True:
                # Set a timeout to check if new devices appeared
                msg = await self.next_message(timeout=0.2)

                match msg:
                    case Shutdown():
                        break
                    case DeviceScanRequest():
                        await self.scan(duration=msg.duration)
                    case None:
                        pass

                for dev in self.client.devices.values():
                    if dev not in self.devices_seen:
                        # Create components for newly discovered devices
                        self.devices_seen.add(dev)
                        self._new_device(dev)
        finally:
            if self.scan_task is not None:
                self.scan_task.cancel()
                await self.scan_task
                self.scan_task = None
            await self.client.disconnect()
