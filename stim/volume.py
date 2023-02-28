from __future__ import annotations

import numpy


class Volume:
    def __repr__(self):
        return self.__str__()

    def make_array(self, x: numpy.ndarray, sample_rate: int, last_value: float | None) -> numpy.ndarray:
        raise NotImplementedError(f"{self.__class__.__name__}.make_array not implemented")


class Sine(Volume):
    def __init__(
            self,
            vmin: float = 0.9, vmax: float = 1.0, freq: float = 1.0):
        self.vmin = vmin
        self.vmax = vmax
        self.freq = freq

    def __str__(self):
        return f"sine({self.vmin}-{self.vmax}, {self.freq}Hz)"

    def make_array(self, x: numpy.ndarray, sample_rate: int, last_value: float | None) -> numpy.ndarray:
        """
        Compute the volume scaling factor function (from 0 to 1) corresponding
        to the given array (generally generated with `arange(samples_count)`)
        """
        if last_value is not None:
            sync_factor = numpy.arcsin(last_value)
        else:
            sync_factor = 0.0

        volume_factor = 2.0 * numpy.pi * self.freq / sample_rate
        return numpy.sin(x * volume_factor + sync_factor) * (self.vmax - self.vmin) + self.vmin


class RampUp(Volume):
    def __init__(
            self,
            vmin: float = 0.0, vmax: float = 1.0):
        self.vmin = float(vmin)
        self.vmax = float(vmax)

    def __str__(self):
        return f"ramp_up({self.vmin}-{self.vmax})"

    def make_array(self, x: numpy.ndarray, sample_rate: int, last_value: float | None) -> numpy.ndarray:
        """
        Compute the volume scaling factor function (from 0 to 1) corresponding
        to the given array (generally generated with `arange(samples_count)`)
        """
        return numpy.linspace(self.vmin, self.vmax, len(x), dtype=numpy.float32)


class RampDown(Volume):
    def __init__(
            self,
            vmin: float = 0.0, vmax: float = 1.0):
        self.vmin = float(vmin)
        self.vmax = float(vmax)

    def __str__(self):
        return f"ramp_down({self.vmin}-{self.vmax})"

    def make_array(self, x: numpy.ndarray, sample_rate: int, last_value: float | None) -> numpy.ndarray:
        """
        Compute the volume scaling factor function (from 0 to 1) corresponding
        to the given array (generally generated with `arange(samples_count)`)
        """
        return numpy.linspace(self.vmax, self.vmin, len(x), dtype=numpy.float32)
