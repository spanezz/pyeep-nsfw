from __future__ import annotations

from pyeep.app import Message, check_hub
from pyeep.gtk import GLib
from pyeep.inputs.heartrate import HeartBeat
from pyeep.messages import Shortcut
from pyeep.types import Color

from .. import animation, messages, output
from ..muse2 import HeadShaken
from .base import Scene, register


class KeyboardShortcutMixin:
    @check_hub
    def handle_keyboard_shortcut(self, shortcut: str):
        match shortcut:
            case "STOP":
                self.send(messages.Pause(group=1))
            case "CYCLE START":
                self.send(messages.Resume(group=1))
            case "+X":
                self.send(messages.Increment(group=1))
            case "-X":
                self.send(messages.Decrement(group=1))
            case "+Y":
                self.send(messages.Increment(group=2))
            case "-Y":
                self.send(messages.Decrement(group=2))
            case "+Z":
                self.send(messages.Increment(group=3))
            case "-Z":
                self.send(messages.Decrement(group=3))
            case "+A":
                self.send(messages.Increment(group=4))
            case "-A":
                self.send(messages.Decrement(group=4))
            case "PULSE":
                self.send(output.IncreaseGroupPower(
                    group=1,
                    amount=animation.PowerPulse(power=0.3, duration=0.5)))
                self.send(output.SetGroupColor(
                    group=1,
                    color=animation.ColorPulse(color=Color(1, 0, 0), duration=0.5)))
            case "SWIPE UP":
                self.send(messages.Decrement(group=1))
            case "SWIPE DOWN":
                self.send(messages.Increment(group=1))
            case "SWIPE RIGHT":
                self.send(messages.Increment(group=1))
                self.send(messages.Increment(group=1))
            case "SWIPE LEFT":
                self.send(messages.Decrement(group=1))
                self.send(messages.Decrement(group=1))
            case "VOLUME UP":
                self.send(output.SetGroupPower(group=1, power=1))
            case "VOLUME DOWN":
                self.send(output.SetGroupPower(group=1, power=0))
            case "TAP":
                self.send(output.IncreaseGroupPower(
                    group=1,
                    amount=animation.PowerPulse(power=0.3, duration=0.5)))
                self.send(output.SetGroupColor(
                    group=1,
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
            case Shortcut():
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
                            self.send(output.SetGroupColor(
                                group=1,
                                color=animation.ColorPulse(color=color)))
                        case "y":
                            # Yes
                            color = Color(0, value, 0)
                            # self.send(output.SetActiveColor(color=color)
                            self.send(output.SetGroupColor(
                                group=1,
                                color=animation.ColorPulse(color=color)))
            case HeartBeat():
                if self.is_active:
                    self.send(output.SetGroupColor(
                        group=1,
                        color=animation.ColorHeartPulse(
                            color=Color(0.5, 0, 0),
                            duration=60 / msg.sample.rate)))
