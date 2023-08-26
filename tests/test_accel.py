from __future__ import annotations

import math
import unittest

G = 9.81


def compute(x: float, y: float, z: float) -> tuple[float, float]:
    roll = math.atan2(y, z) / math.pi * 180
    pitch = math.atan2(-x, math.sqrt(y*y + z*z)) / math.pi * 180
    return roll, pitch


class TestAccelerometers(unittest.TestCase):
    def test_pitch_roll(self):
        self.assertEqual(compute(0, 0, G), (0, 0))
        self.assertEqual(compute(0, 0, -G), (180, 0))
        self.assertEqual(compute(0, G, 0), (90, 0))
        self.assertEqual(compute(0, -G, 0), (-90, 0))
        self.assertEqual(compute(G, 0, 0), (0, -90))
        self.assertEqual(compute(-G, 0, 0), (0, 90))
