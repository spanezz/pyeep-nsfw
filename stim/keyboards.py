from __future__ import annotations

import evdev

from pyeep.app import Message
from pyeep.evdev import EvdevInput

from .messages import EmergencyStop


class Shortcut(Message):
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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.active = True

    @property
    def description(self) -> str:
        return f"CNC {self.device.name}"

    async def on_evdev(self, ev: evdev.InputEvent):
        if ev.type != evdev.ecodes.EV_KEY:
            return
        if ev.value == 0:
            return
        if (val := self.KEY_MAP.get(ev.code)) is None:
            return
        if val == "EMERGENCY":
            self.send(EmergencyStop())
            return
        if not self.active:
            return
        self.mode(val)

    def mode_default(self, value: str):
        self.send(Shortcut(command=value))


class PageTurner(EvdevInput):
    KEY_MAP = {
        evdev.ecodes.KEY_UP: "CYCLE START",
        evdev.ecodes.KEY_DOWN: "STOP",
        evdev.ecodes.KEY_LEFT: "CYCLE START",
        evdev.ecodes.KEY_RIGHT: "STOP",
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.active = True

    @property
    def description(self) -> str:
        return f"Page Turner {self.device.name}"

    async def on_evdev(self, ev: evdev.InputEvent):
        if not self.active:
            return
        if ev.type != evdev.ecodes.EV_KEY:
            return
        if ev.value == 0:
            return
        if (val := self.KEY_MAP.get(ev.code)) is None:
            return
        self.mode(val)

    def mode_default(self, value: str):
        self.send(Shortcut(command=value))


class RingRemote(EvdevInput):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.active = True

        self.is_down: bool = False
        self.down_first_x: int | None = None
        self.down_first_y: int | None = None
        self.down_last_x: int | None = None
        self.down_last_y: int | None = None
        self.down_time: float | None = None

    @property
    def description(self) -> str:
        return f"Ring Remote {self.device.name}"

    def _process_event(self, ev: evdev.InputEvent) -> str | str:
        """
        Process an event, returning a shortcut name if one triggered
        """
        # See /usr/include/linux/input-event-codes.h

        # https://github.com/LinusCDE/rmTabletDriver/blob/master/tabletDriver.py
        # BTN_TOOL_PEN == 1 means that the pen is hovering over the tablet
        # BTN_TOUCH == 1 means that the pen is touching the tablet

        match ev.type:
            case evdev.ecodes.EV_KEY:
                match ev.code:
                    case evdev.ecodes.BTN_TOUCH:
                        self.is_down = bool(ev.value)
                        if self.is_down:
                            self.down_first_x = None
                            self.down_first_y = None
                            self.down_last_x = None
                            self.down_last_y = None
                            self.down_time = ev.timestamp()
                        else:
                            if self.down_first_x is None:
                                dx = None
                            else:
                                dx = self.down_last_x - self.down_first_x

                            if self.down_first_y is None:
                                dy = None
                            else:
                                dy = self.down_last_y - self.down_first_y

                            # duration = ev.timestamp() - self.down_time

                            if (dx is None or abs(dx) < 30) and (dy is None or abs(dy) < 30):
                                # print("TAP", duration)
                                return "TAP"
                            elif dx is not None and dx < -1000:
                                # print("SWIPE LEFT", duration)
                                return "SWIPE LEFT"
                            elif dx is not None and dx > 1000:
                                # print("SWIPE RIGHT", duration)
                                return "SWIPE RIGHT"
                            elif dy is not None and dy < -1000:
                                # print("SWIPE UP", duration)
                                return "SWIPE UP"
                            elif dy is not None and dy > 1000:
                                # print("SWIPE DOWN", duration)
                                return "SWIPE DOWN"
                            else:
                                self.logger.warning("Unknown gesture dx=%r dy=%r", dx, dy)
                    case evdev.ecodes.BTN_TOOL_PEN:
                        pass
                    case evdev.ecodes.KEY_VOLUMEUP:
                        if ev.value != 0:
                            return "VOLUME UP"
                    case evdev.ecodes.KEY_VOLUMEDOWN:
                        if ev.value != 0:
                            return "VOLUME DOWN"
                    case _:
                        self.logger.warning("Unknown KEY event %r", ev)
            case evdev.ecodes.EV_ABS:
                match ev.code:
                    case evdev.ecodes.ABS_X:
                        if self.down_first_x is None:
                            self.down_first_x = ev.value
                        self.down_last_x = ev.value
                    case evdev.ecodes.ABS_Y:
                        if self.down_first_y is None:
                            self.down_first_y = ev.value
                        self.down_last_y = ev.value
                    case _:
                        self.logger.warning("Unknown ABS event %r", ev)
                        # print("ABS", ev, "::", evdev.categorize(ev))
            case evdev.ecodes.EV_SYN:
                pass
            case evdev.ecodes.EV_MSC:
                match ev.code:
                    case evdev.ecodes.MSC_SCAN:
                        # print("SCAN", ev.value)
                        pass
            case _:
                self.logger.warning("Unknown event %r", ev)
        return None

    async def on_evdev(self, ev: evdev.InputEvent):
        if not self.active:
            return
        if (shortcut := self._process_event(ev)) is None:
            return
        self.mode(shortcut)

    def mode_default(self, value: str):
        self.send(Shortcut(command=value))
