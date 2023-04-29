from __future__ import annotations

from pyeep.app import check_hub, Message
from pyeep.gtk import GLib

from .. import keyboards, messages
from .base import Scene, register


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
