from __future__ import annotations

import argparse
import logging
import sys

from ..app.aio import AIOApp
from ..app.gtk import GtkApp
from ..app.jack import JackApp
from ..gtk import Gtk
from ..outputs.pattern import PatternPlayer
from ..outputs.power import PowerOutputBottom

log = logging.getLogger(__name__)


class App(GtkApp, JackApp, AIOApp):
    def __init__(self, args: argparse.Namespace, **kwargs):
        super().__init__(args, **kwargs)
        self.player = self.add_component(PatternPlayer)
        if args.controller:
            self.add_component(PowerOutputBottom, path=args.controller, output=self.player)

    def build_main_window(self):
        super().build_main_window()

        self.grid = Gtk.Grid()
        self.grid.set_column_homogeneous(True)
        self.window.set_child(self.grid)

        model = self.add_component(
            self.player.get_output_controller(),
            output=self.player)

        self.grid.attach(model.widget, 0, 0, 1, 1)


def main():
    parser = App.argparser(name="stimpattern", description="Generate e-stim audio patterns")
    parser.add_argument("--controller", action="store", metavar="socket", help="Controller socket")
    args = parser.parse_args()

    with App(args, title="E-Stim patterns", application_id="org.enricozini.stimpattern") as app:
        app.main()


if __name__ == "__main__":
    sys.exit(main())
