from __future__ import annotations

import logging
import math
from typing import Callable, Generator, Generic, TypeVar

from pyeep.gtk import GLib

from .types import Color

log = logging.getLogger(__name__)


T = TypeVar("T")


class Animation(Generic[T]):
    def values(self, rate: int) -> Generator[T]:
        raise NotImplementedError(f"{self.__class__.__name__}.values not implemented")


class PowerAnimation(Animation[float]):
    pass


class ColorAnimation(Animation[Color]):
    pass


class PowerPulse(PowerAnimation):
    def __init__(self, *, power: float, duration: float = 0.2, **kwargs):
        super().__init__(**kwargs)
        self.power = power
        self.duration = duration

    def __str__(self):
        return f"PowerPulse(power={self.power}, duration={self.duration})"

    def values(self, rate: int) -> Generator[float]:
        frame_count = math.floor(self.duration * rate)
        for frame in range(frame_count):
            envelope = (frame_count - frame) / frame_count
            yield self.power * envelope
        yield 0


class ColorPulse(ColorAnimation):
    def __init__(self, *, color=Color, duration: float = 0.2, **kwargs):
        super().__init__(**kwargs)
        self.color = color
        self.duration = duration

    def __str__(self):
        return f"ColorPulse(color={self.color}, duration={self.duration})"

    def values(self, rate: int) -> Generator[Color]:
        frame_count = math.floor(self.duration * rate)
        for frame in range(frame_count):
            envelope = (frame_count - frame) / frame_count
            yield Color(self.color[0] * envelope, self.color[1] * envelope, self.color[2] * envelope)
        yield Color(0, 0, 0)


class ColorHeartPulse(ColorAnimation):
    def __init__(self, *, color=Color, duration: float = 0.2, **kwargs):
        super().__init__(**kwargs)
        self.color = color
        self.duration = duration

    def __str__(self):
        return f"ColorPulse(color={self.color}, duration={self.duration})"

    def values(self, rate: int) -> Generator[Color]:
        # See https://www.nhlbi.nih.gov/health/heart/heart-beats
        frame_count = math.floor(self.duration * rate)
        atrial_frames = round(frame_count / 3)
        ventricular_frames = frame_count - atrial_frames

        for frame in range(atrial_frames):
            envelope = 0.8 * (atrial_frames - frame) / atrial_frames
            yield Color(self.color[0] * envelope, self.color[1] * envelope, self.color[2] * envelope)

        for frame in range(ventricular_frames):
            envelope = (ventricular_frames - frame) / ventricular_frames
            yield Color(self.color[0] * envelope, self.color[1] * envelope, self.color[2] * envelope)

        yield Color(0, 0, 0)


class Animator(Generic[T]):
    def __init__(self, name: str, rate: int, on_value: Callable[[T], None]):
        self.name = name
        self.rate = rate
        self.timeout: int | None = None
        self.animations: set[Generator[T]] = set()
        self.on_value = on_value

    def __str__(self) -> str:
        return f"Animator({self.name})"

    def start(self, animation: Animation[T]):
        self.animations.add(animation.values(self.rate))
        if self.timeout is None:
            self.timeout = GLib.timeout_add(
                    round(1 / self.rate * 1000),
                    self.on_frame)

    def stop(self):
        if self.timeout is not None:
            GLib.source_remove(self.timeout)
        self.timeout = None
        self.animations = set()

    def merge(self, values: list[T]) -> T:
        raise NotImplementedError(f"{self.__class__.__name__}.merge not implmeented")

    def on_frame(self):
        if not self.animations:
            # All animations have finished
            self.timeout = None
            return False

        values: list[T] = []
        for a in list(self.animations):
            try:
                values.append(next(a))
            except StopIteration:
                self.animations.remove(a)

        if not values:
            # All animations have finished
            self.timeout = None
            return False

        self.on_value(self.merge(values))
        return True


class PowerAnimator(Animator[float]):
    def merge(self, values: list[T]) -> T:
        if len(values) == 1:
            return values[0]
        return sum(values, start=0.0)


class ColorAnimator(Animator[Color]):
    def merge(self, values: list[T]) -> T:
        if len(values) == 1:
            return values[0]
        return sum(values, start=Color(0, 0, 0))
