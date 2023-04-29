from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Type

import aionotify
import evdev

import pyeep.aio
from pyeep.app import Message, Shutdown

from .inputs import Input, InputSetActive
from .messages import EmergencyStop


class CncCommand(Message):
    def __init__(self, *, command: str, **kwargs):
        super().__init__(**kwargs)
        self.command = command

    def __str__(self):
        return super().__str__() + f"(command={self.command})"


class EvdevInput(Input, pyeep.aio.AIOComponent):
    def __init__(self, *, path: Path, device: evdev.InputDevice, **kwargs):
        kwargs.setdefault("name", "kbd_" + path.name)
        super().__init__(**kwargs)
        self.path = path
        self.device = device
        self.active = False

    @pyeep.aio.export
    def is_active(self) -> bool:
        return self.active

    @property
    def description(self) -> str:
        return self.device.name

    async def on_evdev(self, ev: evdev.InputEvent):
        print(repr(ev))

    async def read_events(self):
        try:
            async for ev in self.device.async_read_loop():
                await self.on_evdev(ev)
        except OSError as e:
            self.logger.error("%s: %s", self.path, e)
            self.receive(Shutdown())

    async def run(self):
        async with asyncio.TaskGroup() as tg:
            reader = tg.create_task(self.read_events())
            try:
                while True:
                    match (msg := await self.next_message()):
                        case Shutdown():
                            break
                        case InputSetActive():
                            if msg.input == self:
                                self.active = msg.value
            finally:
                reader.cancel()


class CNCControlPanel(EvdevInput):
    KEY_MAP = {
        evdev.ecodes.KEY_GRAVE: "EMERGENCY",
        # InputEvent(EV_KEY, KEY_LEFTALT, 1)
        evdev.ecodes.KEY_R: "CYCLE START",

        evdev.ecodes.KEY_F5: "SPINDLE ON/OFF",

        # InputEvent(EV_KEY, KEY_RIGHTCTRL, 1)
        evdev.ecodes.KEY_W: "REDO",

        # InputEvent(EV_KEY, KEY_LEFTALT, 1)
        evdev.ecodes.KEY_N: "SINGLE STEP",

        # InputEvent(EV_KEY, KEY_LEFTCTRL, 1)
        evdev.ecodes.KEY_O: "ORIGIN POINT",

        evdev.ecodes.KEY_ESC: "STOP",
        evdev.ecodes.KEY_KPPLUS: "SPEED UP",
        evdev.ecodes.KEY_KPMINUS: "SLOW DOWN",

        evdev.ecodes.KEY_F11: "F+",
        evdev.ecodes.KEY_F10: "F-",
        evdev.ecodes.KEY_RIGHTBRACE: "J+",
        evdev.ecodes.KEY_LEFTBRACE: "J-",

        evdev.ecodes.KEY_UP: "+Y",
        evdev.ecodes.KEY_DOWN: "-Y",
        evdev.ecodes.KEY_LEFT: "-X",
        evdev.ecodes.KEY_RIGHT: "+X",

        evdev.ecodes.KEY_KP7: "+A",
        evdev.ecodes.KEY_Q: "-A",
        evdev.ecodes.KEY_PAGEDOWN: "-Z",
        evdev.ecodes.KEY_PAGEUP: "+Z",
    }

    @property
    def description(self) -> str:
        return f"CNC {self.device.name}"

    async def on_evdev(self, ev: evdev.InputEvent):
        if ev.type == evdev.ecodes.EV_KEY:
            if (val := self.KEY_MAP.get(ev.code)):
                match val:
                    case "EMERGENCY":
                        self.send(EmergencyStop())
                    case _:
                        if self.active:
                            self.send(CncCommand(command=val))


class DeviceManager(pyeep.aio.AIOComponent):
    DEVICE_MAP: dict[str, Type[Input]] = {
        "usb-04d9_1203-event-kbd": CNCControlPanel,
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.components: dict[Path, Input] = {}
        self.root = Path('/dev/input/by-id')
        self.watcher = aionotify.Watcher()

    async def device_added(self, path: Path):
        if path in self.components:
            return

        if (component_cls := self.DEVICE_MAP.get(path.name)) is None:
            return

        try:
            device = evdev.InputDevice(path)
        except PermissionError:
            self.logger.debug("%s: insufficient permissions to access evdev device", path)
            return

        self.logger.info("%s: evdev device added", path)
        component = self.hub.app.add_component(component_cls, path=path, device=device)
        self.components[path] = component

    async def device_removed(self, path: Path):
        self.logger.info("%s: evdev device removed", path)
        if (component := self.components.get(path)) is not None:
            component.receive(Shutdown())

    async def watcher_task(self):
        self.watcher.watch(
            alias='devices',
            path=self.root.as_posix(),
            flags=aionotify.Flags.CREATE | aionotify.Flags.DELETE | aionotify.Flags.MOVED_TO)
        await self.watcher.setup(asyncio.get_event_loop())

        # Enumerate existing devices
        for path in self.root.iterdir():
            if path.name.startswith("."):
                continue
            await self.device_added(path)

        try:
            while True:
                event = await self.watcher.get_event()
                if event.name.startswith("."):
                    continue

                if event.flags & (aionotify.Flags.CREATE | aionotify.Flags.MOVED_TO):
                    await self.device_added(self.root / event.name)
                elif event.flags & aionotify.Flags.DELETE:
                    await self.device_removed(self.root / event.name)
        except asyncio.CancelledError:
            pass
        finally:
            self.watcher.close()

    async def run(self):
        async with asyncio.TaskGroup() as tg:
            device_watcher = tg.create_task(self.watcher_task())

            try:
                while True:
                    match await self.next_message():
                        case Shutdown():
                            break
            finally:
                device_watcher.cancel()
