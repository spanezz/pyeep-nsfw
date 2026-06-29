import asyncio
import argparse
from typing import override, Any, Unpack

import buttplug as bp

from pyeep.animator import PowerAnimator
from pyeep.app.base import BaseAppArgs
from pyeep.models.animation import AnimationPrimitive
from pyeep.models.messages import Message
from pyeep.nodes import PublicComponent, ComponentArgs, Hub
from pyeep.models.messages.power import SetPower
from pyeep.app.asynccmd import ApplicationAsyncCmdClientApp

# from .messages import HeartBeat, Sample


class Device(PublicComponent):
    def __init__(self, bp_dev: bp.ButtplugDevice, *, hub: Hub) -> None:
        super().__init__(name=bp_dev.name, hub=hub)
        self.dev = bp_dev
        self.outputs: list[Output] = []
        for feature in self.dev.features.values():
            if not feature.outputs:
                continue
            for output_type, output in feature.outputs.items():
                self.outputs.append(
                    Output(
                        feature,
                        name=output_type,
                        hub=self.hub,
                        namespace=f"{self.routing_key}.{feature.index}",
                    )
                )

    async def add_outputs_to_hub(self) -> None:
        """Register the component's outputs in the hub."""
        async with asyncio.TaskGroup() as tg:
            for output in self.outputs:
                tg.create_task(self.hub.add_component(output))

    async def remove_outputs_from_hub(self) -> None:
        """Remove the component's outputs from the hub."""
        async with asyncio.TaskGroup() as tg:
            for output in self.outputs:
                tg.create_task(self.hub.remove_component(output))

    # @override
    # async def receive(self, msg: Message) -> None:
    #   match msg:
    #       TODO: handle emergency stops


class Output(PublicComponent):
    hub: "Buttplug"

    def __init__(
        self, feature: bp.DeviceFeature, **kwargs: Unpack[ComponentArgs]
    ) -> None:
        super().__init__(**kwargs)
        self.feature = feature
        #: Power set by non-animated commands
        self.base_power: float = 0.0
        self.animator = PowerAnimator(
            name="power", frame_duration_ns=50_000_000
        )

    async def animator_task(self) -> None:
        async for value in self.animator.values():
            await self.set_power(self.base_power + value)

    async def set_power(self, value: float) -> None:
        cmd = bp.DeviceOutputCommand(bp.OutputType(self.name), float(value))
        await self.feature.run_output(cmd)

    @override
    async def init(self) -> None:
        await super().init()
        await self.start_task(self.animator_task())

    @override
    async def receive(self, msg: Message) -> None:
        match msg:
            case SetPower():
                match msg.power:
                    case float():
                        self.base_power = msg.power
                        if not self.animator.running:
                            await self.set_power(msg.power)
                    case AnimationPrimitive():
                        self.hub.interface.term.add_line(
                            [
                                (
                                    "",
                                    f"Animate {msg.power}.",
                                )
                            ]
                        )
                        self.animator.add_at_next_tick(
                            msg.power.get_animation()
                        )


class Buttplug(ApplicationAsyncCmdClientApp):
    """Inspect the pyeep system."""

    def __init__(self, **kwargs: Unpack[BaseAppArgs]) -> None:
        super().__init__(**kwargs)
        self.client = bp.ButtplugClient("NSFW buttplug component")
        self.client.on_device_added = self.on_device_added
        self.client.on_device_removed = self.on_device_removed
        self.client.on_scanning_finished = self.on_scanning_finished
        self.client.on_server_disconnect = self.on_server_disconnect
        # Connected devices
        self.devices: dict[int, Device] = {}

    @override
    @classmethod
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
        component = Device(dev, hub=self)
        self.devices[dev.index] = component
        await self.add_component(component)
        await component.add_outputs_to_hub()

    async def on_device_removed(self, dev: bp.ButtplugDevice) -> None:
        self.log.info("Device removed: %s", dev.name)
        if component := self.devices.pop(dev.index, None):
            await component.remove_outputs_from_hub()
            await self.remove_component(component)

    async def on_scanning_finished(self) -> None:
        self.log.info("Device scanning finished.")

    async def on_server_disconnect(self) -> None:
        self.log.info("Buttplug server disconnected.")

    @override
    async def init(self) -> None:
        await super().init()
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

    async def cmd_scan(self, duration: float | None = None) -> None:
        """
        Start a scan for devices.

        Usage: scan [secs]

        Scan for the given number of seconds, 5 by default
        """
        duration = duration or 5.0
        self.main_task_group.create_task(self.scan_thread(duration))

    async def cmd_connect(self) -> None:
        """(re)connect to Intiface Central."""
        await self.client.disconnect()
        await self.client.connect(self.args.bp)

    async def cmd_ls(self) -> None:
        """List connected devices."""
        for name, component in self.devices.items():
            dev = component.dev
            self.interface.term.add_line(
                [
                    ("", str(dev.index)),
                    ("", ": "),
                    ("bold", dev.display_name or dev.name),
                ]
            )

    async def cmd_info(self, arg: int | None = None) -> None:
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
                await self.interface.print_usage(self.cmd_info)
                return
        else:
            index = int(arg)
        dev = self.devices[index].dev

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

    async def cmd_vibrate(self, name: str, value: float) -> None:
        """
        Send a vibration command to the given device:feature.

        Usage: vibrate dev:feat value
        """
        devidx, featidx = (int(x) for x in name.split(":", 1))
        dev = self.devices[devidx].dev
        feat = dev.features[featidx]

        cmd = bp.DeviceOutputCommand(bp.OutputType.VIBRATE, value)
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

    async def cmd_stop(self, name: str | None = None) -> None:
        """
        Stop the given device:feature.

        Usage: stop [dev:feat]

        Stop all devices if no argument is given.
        """
        if name is None:
            async with asyncio.TaskGroup() as tg:
                for component in self.devices.values():
                    for feat in component.dev.features.values():
                        tg.create_task(feat.stop())
        else:
            devidx, featidx = (int(x) for x in name.split(":", 1))
            dev = self.devices[devidx].dev
            feat = dev.features[featidx]
            await feat.stop()


if __name__ == "__main__":
    Buttplug.run()
