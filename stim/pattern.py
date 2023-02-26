from __future__ import annotations

import io
import random
from typing import TYPE_CHECKING, Generator, Iterator, Optional

import numpy

if TYPE_CHECKING:
    from .player import Player
    from .excitement import Excitement


class Pattern:
    """
    Abstract interface for a wave generator
    """
    def __init__(self, description: str):
        self.player: "Player"
        self.channel_name: str
        self.buffer = io.BytesIO()
        self.description = description
        self.is_silence = False
        self._iter_waves: Optional[Iterator[numpy.ndarray]] = None
        self.current_wave: Optional[numpy.ndarray] = None
        self.read_offset: int = 0
        self.ended: bool = False

    def set_player(self, player: "Player", channel_name: str):
        self.player = player
        self.channel_name = channel_name

    def on_heartbeat_sample(self, excitement: Excitement):
        """
        Hook called when a new heartbeat sample arrives
        """
        # Do nothing by default
        pass

    def generate(self) -> Generator[numpy.ndarray, None, None]:
        raise NotImplementedError(f"{self.__class__.__name__}.generate not implemented")

    def _next_wave(self) -> bool:
        """
        Move self.current_wave to the next wave, or set self.ended if the
        generator is done.

        Returns True if there is a current wave to be read
        """
        if self._iter_waves is None:
            self._iter_waves = iter(self.generate())
        try:
            self.current_wave = next(self._iter_waves)
            self.read_offset = 0
            return True
        except StopIteration:
            self.ended = True
            return False

    def announce(self):
        if self.is_silence:
            return
        self.player.announce_pattern(self)

    def read(self, nsamples: int) -> numpy.ndarray:
        """
        Return an array of at most `nsamples` samples from this pattern.

        If the pattern terminates before the given number of samples, the
        returned array may be shorter than nsamples
        """
        # Shortcut: wave queue is empty
        if self.ended:
            return numpy.empty(0, dtype=self.player.numpy_type)

        if self.current_wave is None:
            if not self._next_wave():
                return numpy.empty(0, dtype=self.player.numpy_type)

        # Shortcut: first wave has enough data
        if len(self.current_wave) >= self.read_offset + nsamples:
            res = self.current_wave[self.read_offset:self.read_offset + nsamples]
            self.read_offset += nsamples
            return res

        # Incrementally build a samples array
        res = numpy.empty(0, self.player.numpy_type)
        while (size := nsamples - len(res)) > 0:
            if self.ended:
                # No more waves available
                return res
            elif self.read_offset >= len(self.current_wave):
                # Current wave is exausted, skip to the next one
                self._next_wave()
            else:
                # Take from current wave
                chunk = self.current_wave[self.read_offset:self.read_offset + size]
                self.read_offset += len(chunk)
                res = numpy.append(res, chunk)

        return res

    @property
    def data(self):
        return self.buffer.getvalue()

    def silence(self, *, duration: float) -> numpy.ndarray:
        self.player.wave_delta_arcsin = 0
        return numpy.zeros(round(duration * self.player.sample_rate), dtype=self.player.numpy_type)

    def wave(self, *, volume: float = 1.0, duration: float = 1.0, freq: float = 440.0) -> numpy.ndarray:
        if not duration:
            return numpy.empty(0, dtype=self.player.numpy_type)

        samples_count = round(duration * self.player.sample_rate)
        factor = 2.0 * numpy.pi * freq / self.player.sample_rate
        wave = numpy.sin(
                numpy.arange(samples_count, dtype=self.player.numpy_type)
                * factor + self.player.wave_delta_arcsin) * volume
        self.player.wave_delta_arcsin = numpy.arcsin(wave[-1])
        return wave

    def wavy_wave(
            self, *,
            volume_min: float = 0.9, volume_max: float = 1.0, volume_freq: float = 1.0,
            duration: float = 1.0, freq: float = 440.0) -> numpy.ndarray:
        if not duration:
            return numpy.empty(0, dtype=self.player.numpy_type)

        samples_count = round(duration * self.player.sample_rate)
        x = numpy.arange(samples_count, dtype=self.player.numpy_type)
        volume_factor = 2.0 * numpy.pi * volume_freq / self.player.sample_rate
        volume = numpy.sin(x * volume_factor) * (volume_max - volume_min) + volume_min
        factor = 2.0 * numpy.pi * freq / self.player.sample_rate
        wave = numpy.sin(x * factor + self.player.wave_delta_arcsin) * volume
        self.player.wave_delta_arcsin = numpy.arcsin(wave[-1])
        return wave


class Silence(Pattern):
    def __init__(self, *, duration: float = 1.0):
        super().__init__(f"{duration:.2f}s of silence")
        self.is_silence = True
        self.duration = duration

    def generate(self) -> Generator[numpy.ndarray, None, None]:
        yield self.silence(duration=self.duration)


class Wave(Pattern):
    def __init__(
            self, *,
            volume: float = 1.0,
            duration: float = 1.0,
            freq: float = 440.0):
        """
        Wave `duration` seconds long
        """
        super().__init__(f"wave {duration=:.2f}s {volume=} {freq=}")
        self.volume = volume
        self.duration = duration
        self.freq = freq

    def generate(self) -> Generator[numpy.ndarray, None, None]:
        yield self.wave(volume=self.volume, duration=self.duration, freq=self.freq)


class WavyWave(Pattern):
    def __init__(
            self, *,
            volume_min: float = 0.9,
            volume_max: float = 1.0,
            volume_freq: 1.0,
            duration: float = 1.0,
            freq: float = 440.0):
        """
        Wave `duration` seconds long
        """
        super().__init__(f"wavy_wave {duration=:.2f}s {volume_min=} {volume_max=} {freq=}")
        self.volume_min = volume_min
        self.volume_max = volume_max
        self.volume_freq = volume_freq
        self.duration = duration
        self.freq = freq

    def generate(self) -> Generator[numpy.ndarray, None, None]:
        yield self.wavy_wave(
                volume_min=self.volume_min, volume_max=self.volume_max, volume_freq=self.volume_freq,
                duration=self.duration, freq=self.freq)


class Pulses(Pattern):
    def __init__(
            self, *,
            volume: float = 1.0,
            duration: float = 1.0,
            freq: float = 440.0,
            gap: float = 0.1,
            count: int = 1):
        """
        Train of pulses, each `duration` seconds long, followed by a `gap` with
        the given length in seconds
        """
        super().__init__(f"{count} pulses {duration=:.2f}s {volume=} {freq=} {gap=}s")
        self.volume = volume
        self.duration = duration
        self.freq = freq
        self.gap = gap
        self.count = count

    def generate(self) -> Generator[numpy.ndarray, None, None]:
        for i in range(self.count):
            if i > 0:
                yield self.silence(duration=self.gap)
            yield self.wave(volume=self.volume, duration=self.duration, freq=self.freq)


class ChaosPulses(Pattern):
    def __init__(
            self, *,
            volume: tuple[float, float] = (0.9, 1.0, 1.0),
            duration: tuple[float, float] = (1.0, 1.0),
            freq: tuple[float, float] = [200.0, 5000.0],
            gap: tuple[float, float] = [0.1, 0.1],
            count: int = 1):
        """
        Train of pulses, with duration, volume, frequency and gap randomly
        selected from the given intervals
        """
        super().__init__(f"{count} chaotic pulses {duration=}s {volume=} {freq=} {gap=}s")
        self.volume = volume
        self.duration = duration
        self.freq = freq
        self.gap = gap
        self.count = count

    def generate(self) -> Generator[numpy.ndarray, None, None]:
        for i in range(self.count):
            if i > 0:
                yield self.silence(duration=self.gap)
            yield self.wave(
                    volume=random.triangular(*self.volume),
                    duration=random.uniform(*self.duration),
                    freq=random.uniform(*self.freq))


class PatternSequence(Pattern):
    """
    Pattern that generates a sequence of subpatterns
    """
    def patterns(self) -> Generator[Pattern, None, None]:
        raise NotImplementedError(f"{self.__class__.__name__}.pattern_sequence not implemented")

    def generate(self) -> Generator[numpy.ndarray, None, None]:
        for pattern in self.patterns():
            pattern.set_player(self.player, self.channel_name)
            pattern.announce()
            yield from pattern.generate()
