from __future__ import annotations

import asyncio
import contextlib
import os
import threading
import time
from typing import Optional

import pyaudio

from stim.player import Player
from stim.heart import Excitement


@contextlib.contextmanager
def silence_output():
    """
    Temporarily redirect stdout and stderr to /dev/null
    """
    # See https://stackoverflow.com/questions/67765911/how-do-i-silence-pyaudios-noisy-output
    null_fds = [os.open(os.devnull, os.O_RDWR) for x in range(2)]
    save_fds = [os.dup(1), os.dup(2)]

    try:
        os.dup2(null_fds[0], 1)
        os.dup2(null_fds[1], 2)

        yield
    finally:
        os.dup2(save_fds[0], 1)
        os.dup2(save_fds[1], 2)

        for fd in null_fds:
            os.close(fd)


class Stim(Player, threading.Thread):
    def __init__(self) -> None:
        super().__init__()
        with silence_output():
            self.audio = pyaudio.PyAudio()
        self.stream: Optional[pyaudio.Stream] = None
        self.shutting_down = False
        self.heartbeat_socket: Optional[str] = None
        self.excitement: Optional[Excitement] = None

    def on_heartbeat_sample(self):
        for pattern in self.channels:
            pattern.on_heartbeat_sample()

    async def monitor_heartbeat(self):
        if self.heartbeat_socket is None:
            return

        self.excitement = Excitement(quiet=False)
        self.excitement.on_sample = self.on_heartbeat_sample
        await self.excitement.read_socket(self.heartbeat_socket)

    async def wait_for_patterns(self):
        while not all(c.ended for c in self.channels):
            await asyncio.sleep(0.2)

    async def loop(self):
        self.start()
        await asyncio.gather(self.monitor_heartbeat(), self.wait_for_patterns())

    def shutdown(self):
        print("shutting down")
        self.shutting_down = True
        if self.stream:
            while self.stream.is_active():
                time.sleep(0.1)
            self.stream.stop_stream()
            self.stream.close()
        self.join()

        self.audio.terminate()

    def _stream_callback(self, in_data, frame_count: int, time_info, status) -> tuple[bytes, int]:
        if self.shutting_down:
            return bytes(), pyaudio.paComplete
        return self.get_samples(frame_count).tobytes(), pyaudio.paContinue

    def run(self):
        # for paFloat32 sample values must be in range [-1.0, 1.0]
        self.stream = self.audio.open(
                format=pyaudio.paFloat32,
                channels=len(self.channels),
                rate=self.sample_rate,
                output=True,
                # See https://stackoverflow.com/questions/31391766/pyaudio-outputs-slow-crackling-garbled-audio
                frames_per_buffer=4096,
                stream_callback=self._stream_callback)
