from __future__ import annotations

import asyncio
import importlib
import json
from typing import Type

import pyeep.outputs.base
from pyeep.component.aio import AIOComponent
from pyeep.component.base import check_hub, export
from pyeep.gtk import GLib, Gtk
from pyeep.messages import Configure, Message, Shutdown
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
            self.logger.error("RS0")
            while (line := await self.proc.stdout.readline()):
                self.logger.error("RS1 %s", line)
                # TODO: dedup
                try:
                    msg_dict = json.loads(line)
                    module_name = msg_dict.pop("__module__")
                    class_name = msg_dict.pop("__class__")
                    # msg_dict.pop("src", None)
                    msg_dict["src"] = self
                except Exception as e:
                    self.logger.error("message malformed: %r: %s", line.strip(), e)
                    continue

                try:
                    mod = importlib.import_module(module_name)
                    cls = getattr(mod, class_name)
                except Exception as e:
                    self.logger.error("cannot find module class %s.%s: %s", module_name, class_name, e)
                    continue

                try:
                    msg = cls(**msg_dict)
                except Exception as e:
                    self.logger.error("cannot instantiate message: %s", e)
                    continue
                self.logger.error("RS2 %s", msg)
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
            print("RUN4")
            if self.read_stdin_task is not None:
                self.read_stdin_task.cancel()
                await self.read_stdin_task
                self.read_stdin_task = None
