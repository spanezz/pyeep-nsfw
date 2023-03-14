from __future__ import annotations

import asyncio
import json
from typing import NamedTuple


class HeartSample(NamedTuple):
    # UNIX timestamp in nanoseconds
    time: int
    rate: float
    rr: tuple[float] = ()


class HeartReceiver:
    def __init__(self):
        self.samples: list[HeartSample] = []

    async def process_sample(self, sample: HeartSample):
        pass

    async def read_socket(self, socket_name: str):
        reader, writer = await asyncio.open_unix_connection(socket_name)
        initial = json.loads(await reader.readline())
        for sample in (HeartSample(*s) for s in initial["last"]):
            self.samples.append(sample)
            await self.process_sample(sample)

        while not self.shutting_down and (line := await reader.readline()):
            sample = HeartSample(*json.loads(line))
            self.samples.append(sample)
            await self.process_sample(sample)

    async def read_file(self, pathname: str):
        with open(pathname, "rt") as fd:
            for line in fd:
                sample = HeartSample(*json.loads(line))
                self.samples.append(sample)
                await self.process_sample(sample)
