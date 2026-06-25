import asyncio
from typing import override

from pyeep.models.messages import Message
from pyeep.models.scene import SingleTargetSceneDescription
from pyeep.scenes.base import WebSceneSingleTarget
from pyeep.joystick.messages import JoystickTriggerEvent, JoystickStickEvent
from nsfw.messages import RestimCommand


class Description(SingleTargetSceneDescription):
    """Heartbeat scene description."""


@Description.scene
class SceneHeartbeat(WebSceneSingleTarget[Description]):
    """Pulse lights in sync with heartbeat."""

    async def set_channel(
        self, channel: str, value: float, duration: int = 0
    ) -> None:
        await self.send_command(
            RestimCommand(
                dst=self.hub.groups.dst(*self.desc.targets),
                channel=channel,
                value=value,
                duration=duration,
            )
        )

    @override
    async def receive(self, msg: Message) -> None:
        match msg:
            case JoystickTriggerEvent():
                match msg.trigger:
                    case "LT":
                        await self.set_channel("P0", value=(msg.value + 1) / 2)
                    case "RT":
                        await self.set_channel("V0", value=(msg.value + 1) / 2)
            case JoystickStickEvent():
                match msg.stick:
                    case "LS":
                        await self.set_channel("L1", value=(-msg.x + 1) / 2)
                        await self.set_channel("L0", value=(-msg.y + 1) / 2)
                    case "RS":
                        await self.set_channel("C0", value=(msg.y + 1) / 2)

    @override
    async def main(self) -> None:
        await asyncio.Event().wait()
