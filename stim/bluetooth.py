from __future__ import annotations

import asyncio
import re
from typing import Type

import bleak
import bleak.assigned_numbers

import pyeep.aio
from pyeep.app import Message, Shutdown


re_mangle = re.compile(r"[^\w]+")


class BluetoothDisconnect(Message):
    pass


class BluetoothComponent(pyeep.aio.AIOComponent):
    def __init__(self, device: bleak.backends.device.BLEDevice, **kwargs):
        kwargs.setdefault("name", re_mangle.sub("_", f"bt_{device.name}_{device.address}"))
        super().__init__(**kwargs)
        self.device = device
        self.client = bleak.BleakClient(
            self.device,
            disconnected_callback=self._on_disconnect,
        )
        self.connect_task: asyncio.Task | None = None
        self.task_group = asyncio.TaskGroup()

    def _on_disconnect(self, client: bleak.BleakClient):
        self.receive(BluetoothDisconnect())

    async def _connect(self):
        """
        Connect to the device, waiting for it to come back in range if not
        reachable
        """
        while True:
            self.logger.info("(re)connecting device")
            try:
                await self.client.connect()
            except bleak.exc.BleakError as e:
                print(repr(e))
            else:
                break
            await asyncio.sleep(0.3)
        self.logger.info("connected")
        self.connect_task = None

    async def run_start(self):
        self.connect_task = asyncio.create_task(self._connect())

    async def run_end(self):
        if self.connect_task is not None:
            self.connect_task.cancel()
            await self.connect_task
            self.connect_task = None

    async def run_message(self):
        pass

    async def run(self):
        await self.run_start()
        try:
            while True:
                match (msg := await self.next_message()):
                    case Shutdown():
                        break
                    case BluetoothDisconnect():
                        self.logger.warning("device disconnected")
                        if self.connect_task is None:
                            self.connect_task = self.task_group.create_task(self._connect())
                    case _:
                        await self.run_message(msg)
        finally:
            await self.run_end()


class Bluetooth(pyeep.aio.AIOComponent):
    def __init__(self, devices: dict[str, Type[BluetoothComponent]], **kwargs):
        super().__init__(**kwargs)
        # Map device MAC addresses to Component classes to use for them
        self.devices = devices
        # Cache of already insantiated components
        self.components: dict[str, BluetoothComponent] = {}
        self.scanner = bleak.BleakScanner(
            self._scanner_event,
            # bleak.exc.BleakError: passive scanning on Linux requires BlueZ >= 5.55 with --experimental enabled
            #   and Linux kernel >= 5.10
            # scanning_mode="passive",
            # bluez={
            #     "or_patterns": [
            #         (0, bleak.assigned_numbers.AdvertisementDataType.FLAGS, b"\x06"),
            #         (0, bleak.assigned_numbers.AdvertisementDataType.FLAGS, b"\x1a"),
            #     ]
            # }
        )
        self.stop_event = asyncio.Event()

    def _scanner_event(
            self,
            device: bleak.backends.device.BLEDevice,
            advertising_data: bleak.backends.scanner.AdvertisementData):
        if (component_cls := self.devices.get(device.address)) is None:
            return

        # Already discovered
        if device.address in self.components:
            return

        # print("DEVICE", device.address, device.name, device.rssi)
        # print("EVENT", repr(device), repr(advertising_data))
        self.components[device.address] = self.hub.app.add_component(
                component_cls, device=device)

    async def _scan(self):
        # TODO: allow to turn scanning on/off
        await self.scanner.start()
        await self.stop_event.wait()
        await self.scanner.stop()

    async def run(self):
        async with asyncio.TaskGroup() as tg:
            scanner = tg.create_task(self._scan())

            try:
                while True:
                    match await self.next_message():
                        case Shutdown():
                            break
            finally:
                self.stop_event.set()
                scanner.cancel()
