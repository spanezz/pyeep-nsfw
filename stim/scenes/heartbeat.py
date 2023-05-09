from __future__ import annotations

from pyeep.app import Message, check_hub
from pyeep.inputs.heartrate import HeartBeat
from pyeep.types import Color

from .. import animation, output
from .base import Scene, register


@register
class Heartbeat(Scene):
    TITLE = "Heartbeat"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout: int | None = None

    @check_hub
    def receive(self, msg: Message):
        if not self.is_active:
            return
        match msg:
            case HeartBeat():
                if self.is_active:
                    self.send(output.SetGroupColor(
                        group=1,
                        color=animation.ColorHeartPulse(
                            color=Color(0.5, 0, 0),
                            duration=60 / msg.sample.rate)))
