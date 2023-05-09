from __future__ import annotations

from pyeep.app import Message, check_hub
from pyeep.gtk import GLib
from pyeep.messages import Pause, Resume, Shortcut
from pyeep.types import Color

from .. import animation, messages, output
from .base import SingleGroupScene, register


class KeyboardShortcutMixin:
    @check_hub
    def handle_keyboard_shortcut(self, shortcut: str):
        match shortcut:
            case "STOP":
                self.send(Pause(group=self.get_group()))
            case "CYCLE START":
                self.send(Resume(group=self.get_group()))
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
                    group=self.get_group(),
                    amount=animation.PowerPulse(power=0.3, duration=0.5)))
                self.send(output.SetGroupColor(
                    group=self.get_group(),
                    color=animation.ColorPulse(color=Color(1, 0, 0), duration=0.5)))
            case "SWIPE UP":
                self.send(messages.Decrement(group=self.get_group()))
            case "SWIPE DOWN":
                self.send(messages.Increment(group=self.get_group()))
            case "SWIPE RIGHT":
                self.send(messages.Increment(group=self.get_group()))
                self.send(messages.Increment(group=self.get_group()))
            case "SWIPE LEFT":
                self.send(messages.Decrement(group=self.get_group()))
                self.send(messages.Decrement(group=self.get_group()))
            case "VOLUME UP":
                self.send(output.SetGroupPower(group=self.get_group(), power=1))
            case "VOLUME DOWN":
                self.send(output.SetGroupPower(group=self.get_group(), power=0))
            case "TAP":
                self.send(output.IncreaseGroupPower(
                    group=self.get_group(),
                    amount=animation.PowerPulse(power=0.3, duration=0.5)))
                self.send(output.SetGroupColor(
                    group=self.get_group(),
                    color=animation.ColorPulse(color=Color(1, 0, 0), duration=0.5)))


@register
class Default(KeyboardShortcutMixin, SingleGroupScene):
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
