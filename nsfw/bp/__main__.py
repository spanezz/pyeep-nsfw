import asyncio
import argparse
import logging
import time as tm
from typing import override, Any

import buttplug as bp

from pyeep.app.asynccmd import ApplicationAsyncCmdClientApp

# from .messages import HeartBeat, Sample


class Buttplug(ApplicationAsyncCmdClientApp):
    """Inspect the pyeep system."""

    def __init__(self, *, handle_sigterm_sigint: bool = True) -> None:
        super().__init__(
            name="buttplug", handle_sigterm_sigint=handle_sigterm_sigint
        )
        self.client = bp.ButtplugClient("NSFW buttplug component")
        self.client.on_device_added = self.on_device_added
        self.client.on_device_removed = self.on_device_removed
        self.client.on_scanning_finished = self.on_scanning_finished
        self.client.on_server_disconnect = self.on_server_disconnect
        # Connected devices
        self.devices: dict[int, bp.ButtplugDevice] = {}

    def argparser(
        self, description: str | None = None
    ) -> argparse.ArgumentParser:
        parser = super().argparser(description)
        parser.add_argument(
            "--bp",
            type=str,
            default="ws://127.0.0.1:12345",
            help="Buttplug websocket URL to connect to",
        )
        return parser

    async def on_device_added(self, dev: bp.ButtplugDevice) -> None:
        self.log.info("Device added: %s", dev.name)
        self.devices[dev.index] = dev

    async def on_device_removed(self, dev: bp.ButtplugDevice) -> None:
        self.log.info("Device removed: %s", dev.name)
        self.devices.pop(dev.index, None)

    async def on_scanning_finished(self) -> None:
        self.log.info("Device scanning finished.")

    async def on_server_disconnect(self) -> None:
        self.log.info("Buttplug server disconnected.")

    @override
    async def start_main_tasks(self) -> None:
        await super().start_main_tasks()
        await self.client.connect(self.args.bp)

    async def scan_thread(self, duration: float) -> None:
        """
        Scan for devices.

        :param duration: how long to scan, in seconds
        """
        self.log.info("Device scanning started for %.2f seconds.", duration)
        await self.client.start_scanning()
        await asyncio.sleep(duration)
        await self.client.stop_scanning()
        self.log.info("Device scanning stopped after %.2f seconds.", duration)

    async def cmd_scan(self, arg: str | None) -> None:
        """
        Start a scan for devices.

        Usage: scan [secs]

        Scan for the given number of seconds, 5 by default
        """
        duration = float(arg) if arg else 5
        self.main_task_group.create_task(self.scan_thread(duration))

    async def cmd_connect(self, arg: str | None) -> None:
        """(re)connect to Intiface Central."""
        await self.client.disconnect()
        await self.client.connect(self.args.bp)

    async def cmd_ls(self, arg: str | None) -> None:
        """List connected devices."""
        for name, dev in self.devices.items():
            self.interface.term.add_line(
                [
                    ("", str(dev.index)),
                    ("", ": "),
                    ("bold", dev.display_name or dev.name),
                ]
            )

    async def cmd_info(self, arg: str | None) -> None:
        """
        Get information about a device.

        Usage: info [index]

        Index is shown with the `ls` command. The argument is optional if there
        is only one connected device.
        """
        if arg is None:
            if len(self.devices) == 1:
                index = next(iter(self.devices))
            else:
                await self.interface.print_error(
                    "Multiple devices found and no index given."
                )
                await self.print_usage(self.cmd_info)
                return
        else:
            index = int(arg)
        dev = self.devices[index]

        def show_prop(name: str, value: Any) -> None:
            self.interface.term.add_line(
                [("", f" {name}"), ("", ": "), ("bold", str(value))]
            )

        def show_feature(f: bp.DeviceFeature) -> None:
            self.interface.term.add_line(
                [("", f" Feature {f.index}: "), ("bold", str(f.description))]
            )
            if f.inputs:
                for input_type, inp in f.inputs.items():
                    self.interface.term.add_line(
                        [("", "  Input "), ("bold", str(input_type)), ("", ":")]
                    )
                    self.interface.term.add_line(
                        [("", "   Value: "), ("bold", str(inp.value))]
                    )
                    self.interface.term.add_line(
                        [("", "   Command: "), ("bold", str(inp.command))]
                    )

            if f.outputs:
                for output_type, out in f.outputs.items():
                    self.interface.term.add_line(
                        [
                            ("", "  Output "),
                            ("bold", str(output_type)),
                            ("", ":"),
                        ]
                    )
                    self.interface.term.add_line(
                        [("", "   Value: "), ("bold", str(out.value))]
                    )
                    self.interface.term.add_line(
                        [("", "   Duration: "), ("bold", str(out.duration))]
                    )

        show_prop("Index", dev.index)
        show_prop("Name", dev.name)
        show_prop("Display name", dev.display_name)
        show_prop("Message timing gap (ms)", dev.message_timing_gap)
        for feature in dev.features.values():
            show_feature(feature)

    async def cmd_vibrate(self, arg: str | None) -> None:
        """
        Send a vibration command to the given device:feature.

        Usage: vibrate dev:feat value
        """
        if arg is None:
            await self.interface.print_error(
                "Multiple devices found and no index given."
            )
            await self.print_usage(self.cmd_vibrate)
            return
        else:
            outname, value = arg.split(None, 1)
            devidx, featidx = (int(x) for x in outname.split(":", 1))
            dev = self.devices[devidx]
            feat = dev.features[featidx]

        cmd = bp.DeviceOutputCommand(bp.OutputType.VIBRATE, float(value))
        await feat.run_output(cmd)

    # All command types
    # VIBRATE = "Vibrate"
    # ROTATE = "Rotate"
    # OSCILLATE = "Oscillate"
    # CONSTRICT = "Constrict"
    # SPRAY = "Spray"
    # TEMPERATURE = "Temperature"
    # LED = "Led"
    # POSITION = "Position"
    # POSITION_WITH_DURATION = "HwPositionWithDuration"

    async def cmd_stop(self, arg: str | None) -> None:
        """
        Stop the given device:feature.

        Usage: stop dev:feat
        """
        if arg is None:
            await self.interface.print_error(
                "Multiple devices found and no index given."
            )
            await self.print_usage(self.cmd_stop)
            return
        else:
            devidx, featidx = (int(x) for x in arg.split(":", 1))
            dev = self.devices[devidx]
            feat = dev.features[featidx]

        await feat.stop()


if __name__ == "__main__":
    Buttplug.run()
