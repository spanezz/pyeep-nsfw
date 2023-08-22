from __future__ import annotations

from pyeep.component.base import check_hub
from pyeep.messages import Message

from ..joystick import JoystickAxisMoved
from .base import SingleGroupPowerScene, register
from ..outputs.power import SetGroupPower


@register
class JSBondage(SingleGroupPowerScene):
    TITLE = "Joystick bondage"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # self.axes: dict[int, Axis] = {}
        self.timeout: int | None = None
        self.last_delta: dict[int, float] = {4: 0.0, 5: 0.0}

    @check_hub
    def receive(self, msg: Message):
        if not self.is_active:
            return

        match msg:
            case JoystickAxisMoved():
                self.last_delta[msg.axis] = abs(msg.value)

                power = (sum(self.last_delta.values()) / 2)  # ** 2
                self.send(SetGroupPower(group=1, power=power))
