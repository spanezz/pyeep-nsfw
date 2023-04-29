from __future__ import annotations

from pyeep.app import Message


class EmergencyStop(Message):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
