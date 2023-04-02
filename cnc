#!/usr/bin/python3

import argparse
import asyncio
import json
import os
import sys
import threading
from queue import Queue
from typing import Any, IO, Iterator

import libevdev

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


class KeyReader:
    def __init__(self, path: str):
        self.path = path
        self.fd: IO[bytes] | None = None
        self.device: libevdev.Device | None = None

    def __enter__(self):
        self.fd = open(self.path, "rb")
        self.device = libevdev.Device(self.fd)
        self.device.grab()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.device.ungrab()
        self.device = None
        self.fd.close()
        self.fd = None

    def events(self) -> Iterator[dict[str, Any]]:
        for e in self.device.events():
            if e.type == libevdev.EV_KEY:
                if (val := KEY_MAP.get(e.code)):
                    yield {
                        "name": val,
                        "value": e.value,
                        "sec": e.sec,
                        "usec": e.usec,
                    }


class ClientHandler:
    def __init__(self, writer: asyncio.StreamWriter):
        self.writer = writer
        self.queue = Queue()
        self.event = asyncio.Event()

    async def run(self):
        try:
            while True:
                await self.event.wait()
                self.event.clear()
                for event in self.queue.get_nowait():
                    self.writer.write(json.dumps(event).encode() + b"\n")
                await self.writer.drain()
        except Exception as e:
            print("Exception on handler:", e)


class StreamServer:
    def __init__(self, path: str = "cnc.socket"):
        self.path = path
        self.server: asyncio.Server | None = None
        self.handlers: set[ClientHandler] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    def shutdown(self):
        if self.server is None:
            return
        if self.loop is None:
            return

        def close():
            self.server.close()
        self.loop.call_soon_threadsafe(close)

    def on_event(self, event: dict[str, Any]):
        for handler in self.handlers:
            handler.queue.put(event)
            # TODO: it should be enough to have a single event for all handlers
            handler.event.set()

    async def handler(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        handler = ClientHandler(writer)
        self.handlers.add(handler)
        try:
            await handler.run()
        except ConnectionResetError:
            pass
        finally:
            self.handlers.remove(handler)
            writer.close()

    async def run(self):
        self.loop = asyncio.get_event_loop()
        self.server = await asyncio.start_unix_server(self.handler, self.path)
        os.chown(
            self.path,
            int(os.environ["SUDO_UID"]),
            int(os.environ["SUDO_GID"]),
        )
        async with self.server:
            try:
                await self.server.serve_forever()
            except asyncio.CancelledError:
                pass


class ReaderThread:  # (threading.Thread):
    def __init__(self, args: argparse.Namespace):
        super().__init__()
        self.key_reader = KeyReader(args.dev)
        self.stream_server: StreamServer | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

    def shutdown(self):
        # self.key_reader.fd.close()
        # self.key_reader.fd = None
        # self.join()
        pass

    def run(self):
        with self.key_reader:
            for event in self.key_reader.events():
                if self.loop is None:
                    continue
                self.loop.call_soon_threadsafe(self.stream_server.on_event, (event,))


class ServerThread(threading.Thread):
    def __init__(self, args: argparse.Namespace):
        super().__init__()
        self.stream_server = StreamServer(args.socket)
        self.reader_thread: ReaderThread | None = None

    def shutdown(self):
        self.stream_server.shutdown()
        self.join()

    def run(self):
        asyncio.run(self.amain())

    async def amain(self):
        self.reader_thread.loop = asyncio.get_event_loop()
        self.reader_thread.stream_server = self.stream_server
        await self.stream_server.run()


def main():
    parser = argparse.ArgumentParser(description="Read events from a CNC controller keypad")
    parser.add_argument("--dev", metavar="device", action="store", default="/dev/input/by-id/usb-04d9_1203-event-kbd",
                        help="Keyboard device to grab")
    parser.add_argument("--socket", metavar="file.socket", action="store", default="cnc.socket",
                        help="UNIX domain socket to use to multiplex commands to listeners")
    args = parser.parse_args()

    reader_thread = ReaderThread(args)
    server_thread = ServerThread(args)
    server_thread.reader_thread = reader_thread

    server_thread.start()
    # reader_thread.start()

    try:
        reader_thread.run()
    except KeyboardInterrupt:
        pass
    finally:
        reader_thread.shutdown()
        server_thread.shutdown()


if __name__ == "__main__":
    sys.exit(main())
