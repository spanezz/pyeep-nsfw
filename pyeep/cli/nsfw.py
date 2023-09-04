from __future__ import annotations

import argparse
import logging
import sys

import pyeep.bluetooth
import pyeep.inputs.heartrate
import pyeep.inputs.keyboards
import pyeep.inputs.manual
import pyeep.messages
import pyeep.muse2
import pyeep.outputs.buttplug
import pyeep.outputs.coyote
import pyeep.outputs.midisynth
import pyeep.outputs.pattern
import pyeep.pygame
from pyeep.inputs.joystick import Joysticks
from pyeep.outputs.power import PowerOutputTop
from . import play

log = logging.getLogger(__name__)


class PatternPlayer(PowerOutputTop):
    def get_commandline(self):
        return ["python3", "-m", "pyeep.cli.stimpattern", "--controller", self.workdir / "socket"]


class App(play.App):
    def __init__(self, args: argparse.Namespace, **kwargs):
        super().__init__(args, **kwargs)
        self.add_hub(pyeep.pygame.PygameHub)

        self.add_component(pyeep.outputs.buttplug.ButtplugClient, client_name=self.title, iface=self.args.iface)
        # TODO: add devices to an existing Bluetooth component
        # self.add_component(pyeep.bluetooth.Bluetooth, devices=[
        #     pyeep.bluetooth.Device("CD:E3:36:F6:BB:74", pyeep.inputs.heartrate.HeartRateMonitor, ("0000180d-",)),
        #     pyeep.bluetooth.Device("21:04:99:10:35:05", HappyLights),
        #     pyeep.bluetooth.Device("00:55:DA:B7:DE:A1", pyeep.muse2.Muse2),
        #     # pyeep.bluetooth.Device("CF:1E:01:D4:1E:BC", pyeep.outputs.coyote.Coyote),
        # ])
        # self.add_component(HeadPosition)
        # self.add_component(HeadMovement)
        self.add_component(Joysticks)
        self.add_component(PatternPlayer, rate=0)

    def setup_logging(self):
        super().setup_logging()
        if self.args.debug:
            for name in ("websockets.client",
                         "buttplug_client.websocket_connector"):
                logging.getLogger(name).setLevel(logging.INFO)


def main():
    parser = App.argparser(description="Play with nonconventional inputs and outputs")
    parser.add_argument("-i", "--iface", metavar="address", action="store", default="ws://127.0.0.1:12345",
                        help="Intiface Engine address to connect to")
    args = parser.parse_args()

    with App(args, title="Player", application_id="org.enricozini.nsfw") as app:
        app.main()


if __name__ == "__main__":
    sys.exit(main())
