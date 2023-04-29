from __future__ import annotations

from pyeep.app import Message


class EmergencyStop(Message):
    pass


class Pause(Message):
    pass


class Resume(Message):
    pass


class Increment(Message):
    def __init__(self, *, axis: int, **kwargs):
        super().__init__(**kwargs)
        self.axis = axis

    def __str__(self) -> str:
        return super().__str__() + f"(axis={self.axis})"


class Decrement(Message):
    def __init__(self, *, axis: int, **kwargs):
        super().__init__(**kwargs)
        self.axis = axis

    def __str__(self) -> str:
        return super().__str__() + f"(axis={self.axis})"
