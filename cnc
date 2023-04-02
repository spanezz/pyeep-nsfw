#!/usr/bin/python3

import libevdev

fd = open("/dev/input/by-id/usb-04d9_1203-event-kbd", "rb")
device = libevdev.Device(fd)
print(device.name)

device.grab()

KEY_MAP = {
    libevdev.EV_KEY.KEY_GRAVE: "EMERGENCY",
    # InputEvent(EV_KEY, KEY_LEFTALT, 1)
    libevdev.EV_KEY.KEY_R: "CYCLE START",

    libevdev.EV_KEY.KEY_F5: "SPINDLE ON/OFF",

    # InputEvent(EV_KEY, KEY_RIGHTCTRL, 1)
    libevdev.EV_KEY.KEY_W: "REDO",

    # InputEvent(EV_KEY, KEY_LEFTALT, 1)
    libevdev.EV_KEY.KEY_N: "SINGLE STEP",

    # InputEvent(EV_KEY, KEY_LEFTCTRL, 1)
    libevdev.EV_KEY.KEY_O: "ORIGIN POINT",

    libevdev.EV_KEY.KEY_ESC: "STOP",
    libevdev.EV_KEY.KEY_KPPLUS: "SPEED UP",
    libevdev.EV_KEY.KEY_KPMINUS: "SLOW DOWN",

    libevdev.EV_KEY.KEY_F11: "F+",
    libevdev.EV_KEY.KEY_F10: "F-",
    libevdev.EV_KEY.KEY_RIGHTBRACE: "J+",
    libevdev.EV_KEY.KEY_LEFTBRACE: "J-",

    libevdev.EV_KEY.KEY_UP: "+Y",
    libevdev.EV_KEY.KEY_DOWN: "-Y",
    libevdev.EV_KEY.KEY_LEFT: "-X",
    libevdev.EV_KEY.KEY_RIGHT: "+X",

    libevdev.EV_KEY.KEY_KP7: "+A",
    libevdev.EV_KEY.KEY_Q: "-A",
    libevdev.EV_KEY.KEY_PAGEDOWN: "-Z",
    libevdev.EV_KEY.KEY_PAGEUP: "+Z",
}

try:
    while True:
        for e in device.events():
            if e.type == libevdev.EV_KEY:
                if (val := KEY_MAP.get(e.code)):
                    print(val, e.value)
                # else:
                #     print(e)
except KeyboardInterrupt:
    pass
