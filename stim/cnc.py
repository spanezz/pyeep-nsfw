from __future__ import annotations

import asyncio
import json
from pathlib import Path

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


class CncInput(Input, pyeep.aio.AIOComponent):
    def __init__(self, *, path: Path | None = None, **kwargs):
        kwargs.setdefault("name", "cnc")
        super().__init__(**kwargs)
        if path is None:
            self.path = Path("cnc.socket")
        else:
            self.path = path

        self.active = False

    @pyeep.aio.export
    def is_active(self) -> bool:
        return self.active

    async def run(self):
        # Poll socket to connect
        while True:
            try:
                reader, writer = await asyncio.open_unix_connection(self.path)
                break
            except ConnectionRefusedError:
                task_msg = await self.next_message(timeout=0.5)
                if isinstance(task_msg, Shutdown):
                    return

        # Read socket
        task_msg = asyncio.create_task(self.next_message())
        task_line = asyncio.create_task(reader.readline())
        while True:
            done, pending = await asyncio.wait(
                (task_msg, task_line),
                return_when=asyncio.FIRST_COMPLETED)

            if task_msg in done:
                match (msg := task_msg.result()):
                    case Shutdown():
                        break
                    case InputSetActive():
                        if msg.input == self:
                            self.active = msg.value
                task_msg = asyncio.create_task(self.next_message())

            if task_line in done:
                data = json.loads(task_line.result())
                if data["value"] != 0:
                    # print(data)
                    if self.active:
                        match data["name"]:
                            case "EMERGENCY":
                                self.send(EmergencyStop())
                        self.send(CncCommand(command=data["name"]))
                task_line = asyncio.create_task(reader.readline())
