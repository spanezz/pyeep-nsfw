from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pyeep.aio
from pyeep.app import Message, Shutdown


class CncCommand(Message):
    def __init__(self, *, command: str, **kwargs):
        super().__init__(**kwargs)
        self.command = command


class CncReceiver(pyeep.aio.AIOComponent):
    def __init__(self, *, path: Path | None = None, **kwargs):
        kwargs.setdefault("name", "cnc")
        super().__init__(**kwargs)
        if path is None:
            self.path = Path("cnc.socket")
        else:
            self.path = path

    async def run(self):
        # Poll socket to connect
        while True:
            try:
                reader, writer = await asyncio.open_unix_connection(self.path)
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
                match task_msg.result():
                    case Shutdown():
                        break
                task_msg = asyncio.create_task(self.next_message())

            if task_line in done:
                data = json.loads(task_line.result())
                if data["value"] != 0:
                    # print(data)
                    self.send(CncCommand(command=data["name"]))
                task_line = asyncio.create_task(reader.readline())
