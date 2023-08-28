from __future__ import annotations

import argparse
import logging
import sys

from ..app.aio import AIOApp
from ..app.gtk import GtkApp
from ..bluetooth import Bluetooth, Device
from ..component.subprocess import BottomComponent
from ..gtk import Gtk
from ..muse2 import Muse2
from ..inputs.base import InputsModel

log = logging.getLogger(__name__)


class App(GtkApp, AIOApp):
    def __init__(self, args: argparse.Namespace, **kwargs):
        super().__init__(args, **kwargs)
        self.outputs = self.add_component(InputsModel)
        self.add_component(Bluetooth, devices=[
            Device("00:55:DA:B7:DE:A1", Muse2),
        ])
        if args.controller:
            self.add_component(BottomComponent, path=args.controller)

    def setup_logging(self):
        super().setup_logging()
        if self.args.debug:
            for name in ("bleak.backends.bluezdbus.manager",
                         "bleak.backends.bluezdbus.client",
                         "websockets.client",
                         "buttplug_client.websocket_connector"):
                logging.getLogger(name).setLevel(logging.INFO)

    def build_main_window(self):
        super().build_main_window()

        self.grid = Gtk.Grid()
        self.grid.set_column_homogeneous(True)
        self.window.set_child(self.grid)

        self.grid.attach(self.outputs.widget, 0, 0, 1, 1)

        # model = self.add_component(
        #     self.muse2.get_input_controller(),
        #     output=self.muse2)

        # self.grid.attach(model.widget, 0, 0, 1, 1)


def main():
    parser = App.argparser(description="Read information out of a Muse2 headset")
    parser.add_argument("--controller", action="store", metavar="socket", help="Controller socket")
    args = parser.parse_args()

    with App(args, title="Muse2", application_id="org.enricozini.muse2") as app:
        app.main()


if __name__ == "__main__":
    sys.exit(main())
