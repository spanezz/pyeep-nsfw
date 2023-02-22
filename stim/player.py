from __future__ import annotations

import wave
from typing import TYPE_CHECKING

import numpy

if TYPE_CHECKING:
    from .stim import Pattern


class Player:
    """
    Abstract base infrastructure for an pattern player
    """

    def __init__(self, sample_rate: int = 44100, numpy_type=numpy.float32):
        super().__init__()
        # sampling rate, Hz, must be integer
        self.sample_rate = sample_rate
        self.channels: list[Pattern] = []
        self.numpy_type = numpy_type
        # See https://stackoverflow.com/questions/42192239/remove-control-clicking-sound-using-pyaudio-as-an-oscillator
        # This is used to seamlessly join consecutive waveforms
        self.wave_delta_arcsin: int = 0

    def start_mono(self, pattern: Pattern):
        """
        Start playing the given pattern as mono output
        """
        pattern.set_player(self, "mono")
        pattern.announce()
        self.channels.append(pattern)

    def start_stereo(self, left: Pattern, right: Pattern):
        """
        Start playing the given patterns as stereo output
        """
        left.set_player(self, "left")
        left.announce()
        self.channels.append(left)
        right.set_player(self, "right")
        right.announce()
        self.channels.append(right)

    def get_samples(self, frame_count: int) -> numpy.ndarray:
        """
        Get the next `frame_count` frames of audio data to be played
        """
        # See https://stackoverflow.com/questions/5347065/interweaving-two-numpy-arrays
        if len(self.channels) == 1:
            # Shortcut for mono output
            wave = self.channels[0].read(frame_count)
            if wave.size < frame_count:
                # Pad with silence
                wave.resize(frame_count)
            return wave

        # General case for an arbitrary number of channels
        waves = numpy.empty(frame_count * len(self.channels), dtype=self.numpy_type)
        for idx, channel in enumerate(self.channels):
            wave = self.channels[idx].read(frame_count)
            if wave.size < frame_count:
                # Pad with silence
                wave.resize(frame_count)
            waves[idx::len(self.channels)] = wave
        return waves

    async def loop(self):
        """
        Player main loop
        """
        pass


class WaveWriter(Player):
    """
    Player that writes audio data to a .wav audio file
    """
    def __init__(self, filename: str):
        super().__init__()
        self.wav = wave.open(filename, "wb")

    async def loop(self):
        self.wav.setnchannels(len(self.channels))
        self.wav.setsampwidth(1)
        self.wav.setframerate(self.sample_rate)
        while True:
            samples = self.get_samples(self.sample_rate)
            data = (samples * 128 + 128).astype(numpy.int8).tobytes()
            self.wav.writeframesraw(data)
            if all(c.ended for c in self.channels):
                break

    def shutdown(self):
        self.wav.close()
