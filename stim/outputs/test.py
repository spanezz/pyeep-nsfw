from __future__ import annotations

import asyncio
import json
from typing import Type

import pyeep.outputs.base
from pyeep.component.aio import AIOComponent
from pyeep.component.base import export
from pyeep.messages import Shutdown, Jsonable
from ..output import PowerOutput, PowerOutputController


class TestOutput(PowerOutput, AIOComponent):
    """
    Output that does nothing besides tracking the last set power value
    """
    def __init__(self, **kwargs):
        kwargs.setdefault("rate", 20)
        super().__init__(**kwargs)
        self.proc: asyncio.subprocess.Process | None = None
        self.read_stdin_task: asyncio.Task | None = None

    @property
    def description(self) -> str:
        return "Test subprocess"

    def get_output_controller(self) -> Type["pyeep.outputs.base.OutputController"]:
        return PowerOutputController

    @export
    def set_power(self, power: float):
        self.power = power

    async def _read_stdout(self):
        try:
            while (line := await self.proc.stdout.readline()):
                jsonable = json.loads(line)
                cls = Jsonable.jsonable_class(jsonable)
                if cls is None:
                    continue

                jsonable["src"] = self

                try:
                    msg = cls(**jsonable)
                except Exception as e:
                    self.logger.error("cannot instantiate message: %s", e)
                    continue

                self.send(msg)
        finally:
            self.receive(Shutdown())

    async def run(self):
        # TODO: spawn
        # TODO: listen to i/o

        self.proc = await asyncio.create_subprocess_exec(
                "./test-proc",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE)

        self.read_stdin_task = asyncio.create_task(self._read_stdout())

        try:
            while True:
                match (msg := await self.next_message()):
                    case Shutdown():
                        break
                    case _:
                        if msg.src != self:
                            line = json.dumps(msg.as_jsonable()) + "\n"
                            self.proc.stdin.write(line.encode())
                            await self.proc.stdin.drain()
        finally:
            if self.read_stdin_task is not None:
                self.read_stdin_task.cancel()
                await self.read_stdin_task
                self.read_stdin_task = None
