from __future__ import annotations

from pyeep.app import check_hub, Message
from pyeep.gtk import GLib

from .. import keyboards, messages, output, animation, heartbeat
from .base import Scene, register
from ..muse2 import HeadShaken
from ..types import Color


class KeyboardShortcutMixin:
    @check_hub
    def handle_keyboard_shortcut(self, shortcut: str):
        match shortcut:
            case "STOP":
                self.send(messages.Pause())
            case "CYCLE START":
                self.send(messages.Resume())
            case "+X":
                self.send(messages.Increment(axis=0))
            case "-X":
                self.send(messages.Decrement(axis=0))
            case "+Y":
                self.send(messages.Increment(axis=1))
            case "-Y":
                self.send(messages.Decrement(axis=1))
            case "+Z":
                self.send(messages.Increment(axis=2))
            case "-Z":
                self.send(messages.Decrement(axis=2))
            case "+A":
                self.send(messages.Increment(axis=3))
            case "-A":
                self.send(messages.Decrement(axis=3))
            case "PULSE":
                self.send(output.IncreaseActivePower(
                    amount=animation.PowerPulse(power=0.3, duration=0.5)))
                self.send(output.SetActiveColor(
                    color=animation.ColorPulse(color=Color(1, 0, 0), duration=0.5)))
            case "SWIPE UP":
                self.send(messages.Decrement(axis=0))
            case "SWIPE DOWN":
                self.send(messages.Increment(axis=0))
            case "SWIPE RIGHT":
                self.send(messages.Increment(axis=0))
                self.send(messages.Increment(axis=0))
            case "SWIPE LEFT":
                self.send(messages.Decrement(axis=0))
                self.send(messages.Decrement(axis=0))
            case "VOLUME UP":
                self.send(output.SetActivePower(power=1))
            case "VOLUME DOWN":
                self.send(output.SetActivePower(power=0))
            case "TAP":
                self.send(output.IncreaseActivePower(
                    amount=animation.PowerPulse(power=0.3, duration=0.5)))
                self.send(output.SetActiveColor(
                    color=animation.ColorPulse(color=Color(1, 0, 0), duration=0.5)))


@register
class Default(KeyboardShortcutMixin, Scene):
    TITLE = "Default"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Active by default
        self.active.set_state(GLib.Variant.new_boolean(True))

    @check_hub
    def receive(self, msg: Message):
        if not self.is_active:
            return
        match msg:
            case keyboards.Shortcut():
                self.handle_keyboard_shortcut(msg.command)
            case HeadShaken():
                if self.is_active:
                    # Normalized frequency and power
                    # freq: 0..5.5
                    # power: 50..72
                    freq = msg.freq / 5.5
                    if freq < 0:
                        freq = 0
                    elif freq > 1:
                        freq = 1

                    power = (msg.power - 50) / 22
                    if power < 0:
                        power = 0
                    elif power > 1:
                        power = 1

                    value = 0.1 + max(freq, power) * 0.9
                    match msg.axis:
                        case "z":
                            # No
                            color = Color(value, 0, 0)
                            # self.send(output.SetActiveColor(color=color))
                            self.send(output.SetActiveColor(
                                color=animation.ColorPulse(color=color)))
                        case "y":
                            # Yes
                            color = Color(0, value, 0)
                            # self.send(output.SetActiveColor(color=color)
                            self.send(output.SetActiveColor(
                                color=animation.ColorPulse(color=color)))
            case heartbeat.HeartBeat():
                if self.is_active:
                    self.send(output.SetActiveColor(
                        color=animation.ColorHeartPulse(
                            color=Color(0.5, 0, 0),
                            duration=60 / msg.sample.rate)))
