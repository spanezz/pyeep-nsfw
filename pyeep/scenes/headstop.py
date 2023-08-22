from __future__ import annotations

import numpy

from pyeep.component.base import check_hub
from pyeep.messages import Message

from ..muse2 import HeadGyro
from ..output import SetGroupPower
from .base import SingleGroupPowerScene, register


@register
class HeadStop(SingleGroupPowerScene):
    TITLE = "Head stop"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # self.input_rate = 52
        # self.filter_x = dsp.Butterworth(rate=self.input_rate, cutoff=10)
        # self.filter_y = dsp.Butterworth(rate=self.input_rate, cutoff=10)
        # self.filter_z = dsp.Butterworth(rate=self.input_rate, cutoff=10)
        self.last_power = 0.0

    @check_hub
    def receive(self, msg: Message):
        if not self.is_active:
            return

        match msg:
            case HeadGyro():
                min_dps = 0
                max_dps = 20

                dx = max(abs(msg.x)) - 3
                dy = max(abs(msg.y)) - 2.5
                dz = max(abs(msg.z)) - 1.8

                d = numpy.clip((dx + dy + dz - min_dps) / (max_dps - min_dps), 0, 1)
                if d != self.last_power:
                    # print(d, dx, dy, dz)
                    self.send(SetGroupPower(group=1, power=d))
                    self.last_power = d
