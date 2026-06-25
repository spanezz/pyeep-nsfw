import asyncio
import argparse
from typing import override, Any, Unpack

import aiohttp

from pyeep.app.base import BaseAppArgs, AppEventShutdown
from pyeep.models.messages import Message
from pyeep.nodes import PublicComponent, ComponentArgs, Hub
from pyeep.models.messages.power import SetPower
from pyeep.app.asynccmd import ApplicationAsyncCmdClientApp
from nsfw.messages import RestimCommand


class Restim(PublicComponent):
    hub: "TCode"

    def __init__(self, *, addr: str, **kwargs: Unpack[ComponentArgs]) -> None:
        super().__init__(**kwargs)
        self.addr = addr
        self.tcode_ws: aiohttp.ClientWebSocketResponse | None = None

    async def tcode_connect(self) -> None:
        """Connect to the server and handle message traffic."""
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self.addr) as ws:
                try:
                    self.tcode_ws = ws
                    async for wsmsg in ws:
                        match wsmsg.type:
                            case aiohttp.WSMsgType.TEXT:
                                self.log.info("Received: %s", wsmsg.data)
                            case aiohttp.WSMsgType.CLOSE:
                                break
                            case _:
                                self.log.error(
                                    "received unexpected %s message %r",
                                    wsmsg.type,
                                    wsmsg,
                                )
                finally:
                    self.ws = None

    async def main(self) -> None:
        await self.tcode_connect()
        await self.hub.main_event_queue.put(
            AppEventShutdown("Restim server disconnected")
        )

    async def set_channel(
        self, name: str, value: float, duration: int = 0
    ) -> None:
        ivalue = round(value * 100000)
        if ivalue < 0:
            ivalue = 0
        elif ivalue > 99999:
            ivalue = 99999
        cmd = f"{name}{ivalue:05d}"
        if duration > 0:
            cmd += "I{duration}"
        if self.tcode_ws is not None:
            self.log.info("Sending T-code %s", cmd)
            await self.tcode_ws.send_str(cmd)
        else:
            self.log.error("T-Code socket is not connected")

    @override
    async def receive(self, msg: Message) -> None:
        match msg:
            case RestimCommand():
                await self.set_channel(msg.channel, msg.value, msg.duration)


class TCode(ApplicationAsyncCmdClientApp):
    """Send tcode commands over websocekt."""

    def __init__(self, **kwargs: Unpack[BaseAppArgs]) -> None:
        super().__init__(**kwargs)
        self.restim = Restim(name="restim", addr=self.args.ws, hub=self)

    @override
    @classmethod
    def argparser(
        self, description: str | None = None
    ) -> argparse.ArgumentParser:
        parser = super().argparser(description)
        parser.add_argument(
            "--ws",
            type=str,
            default="ws://[::1]:12346/tcode",
            help="Restim t-code websocket URL to connect to",
        )
        return parser

    @override
    async def start_main_tasks(self) -> None:
        await super().start_main_tasks()
        await self.add_component(self.restim)
        await self.start_task(self.restim.main())

    async def cmd_send(self, command: str) -> None:
        """Send a tcode command."""
        if self.restim.tcode_ws is not None:
            await self.restim.tcode_ws.send_str(command)
        else:
            self.log.error("T-Code socket is not connected")


if __name__ == "__main__":
    TCode.run()
