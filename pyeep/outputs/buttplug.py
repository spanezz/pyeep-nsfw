from __future__ import annotations

import asyncio
from typing import Any, Type

import buttplug
import pyeep.outputs
from pyeep.component.aio import AIOComponent
from pyeep.component.base import export, check_hub
from pyeep.component.controller import ControllerWidget
from pyeep.messages.message import Message
from pyeep.messages.component import DeviceScanRequest, Shutdown

from .base import Output, OutputController
from .power import PowerOutput, PowerOutputController
from pyeep.gtk import GLib, Gtk


class SetPower(Message):
    """
    Internal use only
    """

    def __init__(self, *, power: float, **kwargs):
        super().__init__(**kwargs)
        self.power = power

    def __str__(self) -> str:
        return super().__str__() + f"(power={self.power})"


class SetPosition(Message):
    """
    Set the position for a linear actuator.
    """

    def __init__(self, *, time_ms: int, position: float, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.time_ms = time_ms
        self.position = position

    def __str__(self) -> str:
        return super().__str__() + f"(time_ms={self.time_ms}, position={self.position})"


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


class LinearOutputController(OutputController):
    """
    Base controller for linear actuators
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.timeout: int | None = None

        self.position_min = Gtk.Adjustment(
            value=0, lower=0, upper=100, step_increment=5, page_increment=10, page_size=0
        )
        # self.position_min.connect("value_changed", self.on_position_min)

        self.position_max = Gtk.Adjustment(
            value=100, lower=0, upper=100, step_increment=5, page_increment=10, page_size=0
        )
        # self.position_max.connect("value_changed", self.on_position_max)

        self.movement_time = Gtk.Adjustment(
            value=500, lower=0, upper=1000, step_increment=5, page_increment=50, page_size=0
        )
        # self.movement_time.connect("value_changed", self.on_movement_time)

        self.forwards = True

        self.timeout = GLib.timeout_add(self.movement_time.get_value(), self.select_next_target)

    @check_hub
    def select_next_target(self):
        time_ms = int(self.movement_time.get_value())
        if self.forwards:
            target = self.position_max.get_value() / 100.0
            self.output.set_position(time_ms, target)
            self.forwards = False
        else:
            target = self.position_min.get_value() / 100.0
            self.output.set_position(time_ms, target)
            self.forwards = True
        self.timeout = GLib.timeout_add(self.movement_time.get_value(), self.select_next_target)
        return False

    def build(self) -> ControllerWidget:
        cw = super().build()

        grid = Gtk.Grid()
        cw.box.append(grid)

        position_min = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.position_min)
        position_min.set_digits(2)
        position_min.set_draw_value(False)
        position_min.set_hexpand(True)
        # position_min.connect("change-value", self.on_changed)
        grid.attach(position_min, 0, 0, 4, 1)

        position_max = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.position_max)
        position_max.set_digits(2)
        position_max.set_draw_value(False)
        position_max.set_hexpand(True)
        # position_max.connect("change-value", self.on_changed)
        grid.attach(position_max, 0, 1, 4, 1)

        movement_time = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.movement_time)
        movement_time.set_digits(2)
        movement_time.set_draw_value(False)
        movement_time.set_hexpand(True)
        # movement_time.connect("change-value", self.on_changed)
        grid.attach(movement_time, 0, 2, 4, 1)

        return cw


class LinearActuator(Output, AIOComponent):
    """
    Component driving a linear actuator
    """

    def __init__(self, *, actuator: buttplug.client.client.LinearActuator, **kwargs):
        kwargs.setdefault("rate", 20)
        super().__init__(**kwargs)
        self.actuator = actuator

    @property
    def description(self) -> str:
        return f"{self.actuator._device.name} {self.name}"

    def get_output_controller(self) -> Type["pyeep.outputs.base.OutputController"]:
        return LinearOutputController

    @export
    def set_position(self, time_ms: int, position: float):
        self.receive(SetPosition(time_ms=time_ms, position=position))

    async def run(self):
        while True:
            msg = await self.next_message()
            match msg:
                case Shutdown():
                    break
                case SetPosition():
                    await self.actuator.command(msg.time_ms, msg.position)


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
            print(f"* Actuator {a.description} {a.__class__.__name__}")
            self.hub.app.add_component(Actuator, name=f"{name}_act{a.index}", actuator=a)

        for a in dev.linear_actuators:
            print(f"* Linear actuator {a.description} {a.__class__.__name__}")
            self.hub.app.add_component(LinearActuator, name=f"{name}_act{a.index}", actuator=a)

        for a in dev.rotatory_actuators:
            print(f"* Rotatory actuator: {a.description} {a.__class__.__name__}")

        for s in dev.sensors:
            # value = await s.read()
            # print(f"* Sensor: {s.description} {s.__class__.__name__}: {value}")
            print(f"* Sensor: {s.description} {s.__class__.__name__}")

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
