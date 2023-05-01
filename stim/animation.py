from __future__ import annotations

import logging
from typing import Callable, Generic, TypeVar

from pyeep.gtk import GLib

from .types import Color

log = logging.getLogger(__name__)


T = TypeVar("T")


class Animation(Generic[T]):
    def __init__(self):
        self.frame: int = 0
        self.rate: int | None = None

    def start(self, rate: int):
        self.rate = rate
        self.frame = 0

    def next(self) -> T | None:
        frame = self.frame
        self.frame += 1
        return self.get_value(frame)

    def get_value(self, frame: int) -> T | None:
        raise NotImplementedError(f"{self.__class__.__name__}.get_value not implemented")


class PowerAnimation(Animation[float]):
    pass


class ColorAnimation(Animation[Color]):
    pass


class ColorPulse(ColorAnimation):
    def __init__(self, *, color=Color, duration: float = 0.2, **kwargs):
        super().__init__(**kwargs)
        self.color = color
        self.duration = duration

    def start(self, rate: int):
        super().start(rate)
        self.done = False

    def __str__(self):
        return f"ColorPulse(color={self.color}, duration={self.duration})"

    def get_value(self, frame: int) -> Color | None:
        if self.done:
            return None
        t = frame / self.rate
        if t > self.duration:
            self.done = True
            return Color(0, 0, 0)
        envelope = (self.duration - t) / self.duration
        return Color(self.color[0] * envelope, self.color[1] * envelope, self.color[2] * envelope)


class Animator(Generic[T]):
    def __init__(self, rate: int, on_value: Callable[[T], None]):
        self.rate = rate
        self.timeout: int | None = None
        self.animations: set[Animation[T]] = set()
        self.on_value = on_value

    def start(self, animation: Animation[T]):
        animation.start(self.rate)
        self.animations.add(animation)

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
        if len(values) == 1:
            return values[0]
        return sum(values, start=Color(0, 0, 0))

    def on_frame(self):
        if not self.animations:
            # All animations have finished
            self.timeout = None
            return False

        values: list[T] = []
        for a in list(self.animations):
            value = a.next()
            if value is None:
                self.animations.remove(a)
            else:
                values.append(value)

        if not values:
            # All animations have finished
            self.timeout = None
            return False

        self.on_value(self.merge(values))
        return True
