from __future__ import annotations

import logging

import buttplug
import pyeep.aio
from pyeep.app import Message, Shutdown, Component
from pyeep.gtk import Gio, GLib

from .output import NewOutput, Output, SetPower

log = logging.getLogger(__name__)


class ScanRequest(Message):
    def __init__(self, *, scan: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.scan = scan

    def __str__(self):
        return "scan request"


class Actuator(Output, pyeep.aio.AIOComponent):
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

    async def run(self):
        while True:
            msg = await self.next_message()
            match msg:
                case Shutdown():
                    break
                case SetPower():
                    if msg.output == self:
                        await self.actuator.command(msg.power)


class ButtplugClient(pyeep.aio.AIOComponent):
    def __init__(self, client_name: str, iface: str, **kwargs):
        kwargs.setdefault("name", "buttplug_client")
        super().__init__(**kwargs)
        self.client = buttplug.Client(client_name, buttplug.ProtocolSpec.v3)
        self.connector = buttplug.WebsocketConnector(iface, logger=self.logger)
        self.devices_seen: set[buttplug.client.client.Device] = set()

    def _new_device(self, dev: buttplug.client.client.Device):
        name = f"bp_dev{dev.index}"

        for a in dev.actuators:
            actuator = self.hub.app.add_component(Actuator, name=f"{name}_act{a.index}", actuator=a)
            self.send(NewOutput(output=actuator))

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
                # Set a timeout to check if new devices appeared
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


class ScanAction(Component):
    HUB = "gtk"

    def __init__(self, **kwargs):
        kwargs.setdefault("name", "buttplug_scan")
        super().__init__(**kwargs)
        self.action = Gio.SimpleAction.new_stateful(
                name=kwargs["name"],
                parameter_type=None,
                state=GLib.Variant.new_boolean(False))
        self.action.connect("activate", self.on_activate)

    def on_activate(self, action, parameter):
        new_state = not self.action.get_state().get_boolean()
        self.action.set_state(GLib.Variant.new_boolean(new_state))
        self.send(ScanRequest(scan=new_state))
