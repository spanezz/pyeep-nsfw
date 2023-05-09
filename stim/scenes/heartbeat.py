from __future__ import annotations

from pyeep.app import Message, check_hub
from pyeep.gtk import GLib
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
        self.last_rate: int | None = None

    def _check_timeout(self):
        if self.last_rate is None:
            return

        if self.timeout is not None:
            return

        self.timeout = GLib.timeout_add(
                60 / self.last_rate * 1000,
                self._tick)

    def _tick(self):
        if self.last_rate is None:
            return False

        self.send(output.SetGroupColor(
            group=1,
            color=animation.ColorHeartPulse(
                color=Color(0.5, 0, 0),
                duration=0.9 * 60 / self.last_rate)))

        self.timeout = GLib.timeout_add(
                60 / self.last_rate * 1000,
                self._tick)
        return False

    @check_hub
    def receive(self, msg: Message):
        if not self.is_active:
            return
        match msg:
            case HeartBeat():
                if self.is_active:
                    self.last_rate = msg.sample.rate
                    self._check_timeout()
