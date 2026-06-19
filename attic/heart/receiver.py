from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import NamedTuple


class HeartSample(NamedTuple):
    # UNIX timestamp in nanoseconds
    time: int
    rate: float
    rr: tuple[float] = ()


class HeartReceiver:
    def __init__(self, path: Path):
        self.path = path
        self.samples: list[HeartSample] = []
        self.shutting_down = False
        self.realtime = path.suffix == ".socket"

    def shutdown(self):
        self.shutting_down = True

    async def run(self):
        if self.realtime:
            await self.read_socket()
        else:
            await self.read_file()

    async def process_sample(self, sample: HeartSample):
        pass

    async def read_socket(self):
        self.realtime = True
        reader, writer = await asyncio.open_unix_connection(self.path)
        initial = json.loads(await reader.readline())
        for sample in (HeartSample(*s) for s in initial["last"]):
            self.samples.append(sample)
            await self.process_sample(sample)

        while not self.shutting_down and (line := await reader.readline()):
            sample = HeartSample(*json.loads(line))
            self.samples.append(sample)
            await self.process_sample(sample)

    async def read_file(self):
        self.realtime = False
        with open(self.path, "rt") as fd:
            for line in fd:
                sample = HeartSample(*json.loads(line))
                self.samples.append(sample)
                await self.process_sample(sample)
