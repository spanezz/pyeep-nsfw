from __future__ import annotations

from typing import NamedTuple
from pyeep.gtk import Gdk


class Color(NamedTuple):
    red: float = 0
    green: float = 0
    blue: float = 0

    def __str__(self):
        return (
            "#"
            f"{int(round(self.red * 255)):02x}"
            f"{int(round(self.green * 255)):02x}"
            f"{int(round(self.blue * 255)):02x}"
        )

    def as_rgba(self) -> Gdk.RGBA:
        color = Gdk.RGBA()
        color.red = self.red
        color.green = self.green
        color.blue = self.blue
        color.alpha = 1
        return color
