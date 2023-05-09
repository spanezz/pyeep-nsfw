from __future__ import annotations

import logging
import math
from typing import Generator

from pyeep.animation import PowerAnimation, ColorAnimation
from pyeep.types import Color

log = logging.getLogger(__name__)


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
