from __future__ import annotations

import logging

from pyeep.app import Message, Shutdown
import pyeep.aio

log = logging.getLogger(__name__)


class NewOutput(Message):
    def __init__(self, *, output: "Output", **kwargs):
        super().__init__(**kwargs)
        self.output = output

    def __str__(self):
        return super().__str__() + f"({self.output.description})"


class SetPower(Message):
    def __init__(self, *, output: "Output", power: float, **kwargs):
        super().__init__(**kwargs)
        self.output = output
        self.power = power

    def __str__(self) -> str:
        return super().__str__() + f"(power={self.power})"


class Output(pyeep.app.Component):
    """
    Generic base for output components
    """
    def __init__(self, *, rate: int, **kwargs):
        super().__init__(**kwargs)

        # Rate (changes per second) at which this output can take commands
        self.rate = rate

    @property
    def description(self) -> str:
        return self.name


class NullOutput(Output, pyeep.aio.AIOComponent):
    """
    Output that does nothing besides tracking the last set power value
    """
    def __init__(self, **kwargs):
        kwargs.setdefault("rate", 20)
        super().__init__(**kwargs)
        self.power: float = 0.0

    @property
    def description(self) -> str:
        return "Null output"

    async def run(self):
        while True:
            msg = await self.next_message()
            match msg:
                case Shutdown():
                    break
                case SetPower():
                    if msg.output == self:
                        self.power = msg.power
