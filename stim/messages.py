from __future__ import annotations

from pyeep.app import Message


class Increment(Message):
    def __init__(self, *, group: int, **kwargs):
        super().__init__(**kwargs)
        self.group = group

    def __str__(self) -> str:
        return super().__str__() + f"(group={self.group})"


class Decrement(Message):
    def __init__(self, *, group: int, **kwargs):
        super().__init__(**kwargs)
        self.group = group

    def __str__(self) -> str:
        return super().__str__() + f"(group={self.group})"
