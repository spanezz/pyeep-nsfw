from __future__ import annotations

import evdev

from pyeep.evdev import EvdevInput
from pyeep.app import Message

from .messages import EmergencyStop


class CncCommand(Message):
    def __init__(self, *, command: str, **kwargs):
        super().__init__(**kwargs)
        self.command = command

    def __str__(self):
        return super().__str__() + f"(command={self.command})"


class CNCControlPanel(EvdevInput):
    KEY_MAP = {
        evdev.ecodes.KEY_GRAVE: "EMERGENCY",
        # InputEvent(EV_KEY, KEY_LEFTALT, 1)
        evdev.ecodes.KEY_R: "CYCLE START",

        evdev.ecodes.KEY_F5: "SPINDLE ON/OFF",

        # InputEvent(EV_KEY, KEY_RIGHTCTRL, 1)
        evdev.ecodes.KEY_W: "REDO",

        # InputEvent(EV_KEY, KEY_LEFTALT, 1)
        evdev.ecodes.KEY_N: "SINGLE STEP",

        # InputEvent(EV_KEY, KEY_LEFTCTRL, 1)
        evdev.ecodes.KEY_O: "ORIGIN POINT",

        evdev.ecodes.KEY_ESC: "STOP",
        evdev.ecodes.KEY_KPPLUS: "SPEED UP",
        evdev.ecodes.KEY_KPMINUS: "SLOW DOWN",

        evdev.ecodes.KEY_F11: "F+",
        evdev.ecodes.KEY_F10: "F-",
        evdev.ecodes.KEY_RIGHTBRACE: "J+",
        evdev.ecodes.KEY_LEFTBRACE: "J-",

        evdev.ecodes.KEY_UP: "+Y",
        evdev.ecodes.KEY_DOWN: "-Y",
        evdev.ecodes.KEY_LEFT: "-X",
        evdev.ecodes.KEY_RIGHT: "+X",

        evdev.ecodes.KEY_KP7: "+A",
        evdev.ecodes.KEY_Q: "-A",
        evdev.ecodes.KEY_PAGEDOWN: "-Z",
        evdev.ecodes.KEY_PAGEUP: "+Z",
    }

    @property
    def description(self) -> str:
        return f"CNC {self.device.name}"

    async def on_evdev(self, ev: evdev.InputEvent):
        if ev.type == evdev.ecodes.EV_KEY and ev.value != 0:
            if (val := self.KEY_MAP.get(ev.code)):
                match val:
                    case "EMERGENCY":
                        self.send(EmergencyStop())
                    case _:
                        if self.active:
                            self.send(CncCommand(command=val))


class PageTurner(EvdevInput):
    KEY_MAP = {
        evdev.ecodes.KEY_UP: "REDO",
        evdev.ecodes.KEY_DOWN: "STOP",
        evdev.ecodes.KEY_LEFT: "REDO",
        evdev.ecodes.KEY_RIGHT: "STOP",
    }

    @property
    def description(self) -> str:
        return f"Page Turner {self.device.name}"

    async def on_evdev(self, ev: evdev.InputEvent):
        if ev.type == evdev.ecodes.EV_KEY and ev.value != 0:
            if (val := self.KEY_MAP.get(ev.code)):
                match val:
                    case _:
                        if self.active:
                            self.send(CncCommand(command=val))
