import argparse
import importlib
import logging
import pkgutil
import sys
from typing import Type

import pyeep.bluetooth
import pyeep.inputs.heartrate
import pyeep.inputs.keyboards
import pyeep.inputs.manual
import pyeep.messages
import pyeep.pygame
import pyeep.outputs.buttplug
import pyeep.muse2
import pyeep.outputs.midisynth
import pyeep.outputs.pattern
import pyeep.outputs.coyote
from pyeep.app.aio import AIOApp
from pyeep.app.gtk import GtkApp
from pyeep.app.jack import JackApp
from pyeep.component.base import Component
from pyeep.component.configmanager import ConfigManager
from pyeep.gtk import Gio, GLib, Gtk
from pyeep.inputs.base import Input
from pyeep.inputs.joystick import Joysticks
from pyeep.outputs.base import OutputsModel
from pyeep.outputs.happylights import HappyLights
from pyeep import scenes
from pyeep.outputs.power import NullOutput, PowerOutput
from pyeep.component.subprocess import TopComponent

log = logging.getLogger(__name__)


class ScanAction(Component):
    HUB = "gtk"

    def __init__(self, **kwargs):
        kwargs.setdefault("name", "device_scan")
        super().__init__(**kwargs)
        self.action = Gio.SimpleAction.new(
                name=self.name.replace("_", "-"),
                parameter_type=None)
        self.action.connect("activate", self.on_activate)
        self.hub.app.gtk_app.add_action(self.action)

    def on_activate(self, action, parameter):
        self.send(pyeep.messages.DeviceScanRequest(duration=3.0))


class MidiSynthesizer(TopComponent):
    def get_commandline(self):
        return ["python3", "-m", "pyeep.cli.midisynth", "--controller", self.workdir / "socket"]


class MidiInputReader(TopComponent):
    def get_commandline(self):
        return ["python3", "-m", "pyeep.cli.midievents", "--controller", self.workdir / "socket"]


class PatternPlayer(TopComponent, PowerOutput):
    def get_commandline(self):
        return ["python3", "-m", "pyeep.cli.stimpattern", "--controller", self.workdir / "socket"]


class PulsesPlayer(TopComponent, PowerOutput):
    def get_commandline(self):
        return ["python3", "-m", "pyeep.cli.audiopulses", "--controller", self.workdir / "socket"]


class App(GtkApp, JackApp, AIOApp):
    def __init__(self, args: argparse.Namespace, **kwargs):
        super().__init__(args, **kwargs)
        self.add_hub(pyeep.pygame.PygameHub)
        self.add_component(ConfigManager)
        self.outputs = self.add_component(OutputsModel)
        self.inputs: list[Input] = []

        self.action_save_config = Gio.SimpleAction.new(
                name="save-config",
                parameter_type=None)
        self.action_save_config.connect("activate", self.on_save_config)
        self.gtk_app.add_action(self.action_save_config)

        self.add_component(pyeep.outputs.buttplug.ButtplugClient, client_name=self.title, iface=self.args.iface)
        self.add_component(pyeep.inputs.manual.Manual)
        self.add_component(MidiInputReader)
        self.add_component(MidiSynthesizer)
        self.add_component(pyeep.bluetooth.Bluetooth, devices=[
            pyeep.bluetooth.Device("CD:E3:36:F6:BB:74", pyeep.inputs.heartrate.HeartRateMonitor, ("0000180d-",)),
            pyeep.bluetooth.Device("21:04:99:10:35:05", HappyLights),
            pyeep.bluetooth.Device("00:55:DA:B7:DE:A1", pyeep.muse2.Muse2),
            # pyeep.bluetooth.Device("CF:1E:01:D4:1E:BC", pyeep.outputs.coyote.Coyote),
        ])
        # self.add_component(HeadPosition)
        # self.add_component(HeadMovement)
        self.add_component(Joysticks)
        self.add_component(pyeep.inputs.evdev.EvdevDeviceManager, device_map={
            "usb-04d9_1203-event-kbd": pyeep.inputs.keyboards.CNCControlPanel,
            "bluetooth-40:28:c6:3f:39:91:1b-kbd": pyeep.inputs.keyboards.PageTurner,
            "bluetooth-22c:28:c6:3f:39:91:1b": pyeep.inputs.keyboards.RingRemote,
        })
        self.add_component(NullOutput, name="null_output")
        self.add_component(PulsesPlayer, rate=0)
        self.add_component(PatternPlayer, rate=0)
        # self.add_component(pyeep.outputs.test.TestOutput)

    def on_save_config(self, action, parameter):
        self.send(pyeep.messages.ConfigSaveRequest())

    def setup_logging(self):
        super().setup_logging()
        if self.args.debug:
            for name in ("bleak.backends.bluezdbus.manager",
                         "bleak.backends.bluezdbus.client",
                         "websockets.client",
                         "buttplug_client.websocket_connector"):
                logging.getLogger(name).setLevel(logging.INFO)

    def _add_input_ui(self, input: Input):
        input_controller = self.add_component(input.get_controller(), component=input)
        self.inputs_box.append(input_controller.widget)

    def _add_input(self, input: Input):
        # TODO: also remove on remove_component
        self.inputs.append(input)
        if hasattr(self, "inputs_box"):
            self._add_input_ui(input)

    def add_component(self, component_cls: Type[Component], **kwargs) -> Component:
        component = super().add_component(component_cls, **kwargs)
        match component:
            case Input():
                GLib.idle_add(self._add_input, component)
        return component

    def build_main_window(self):
        super().build_main_window()

        self.grid = Gtk.Grid()
        self.grid.set_column_homogeneous(True)
        self.window.set_child(self.grid)

        self.frame_inputs = Gtk.Frame(label="Inputs")
        self.frame_inputs.set_vexpand(True)
        self.inputs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.frame_inputs.set_child(self.inputs_box)
        for inp in self.inputs:
            self._add_input_ui(inp)

        self.frame_scenes = Gtk.Frame(label="Scenes")
        self.frame_scenes.set_vexpand(True)
        self.scenes_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.frame_scenes.set_child(self.scenes_box)

        self.grid.attach(self.frame_inputs, 0, 0, 1, 1)
        self.grid.attach(self.frame_scenes, 1, 0, 1, 1)
        self.grid.attach(self.outputs.widget, 2, 0, 1, 1)

        # Instantiate scenes
        for importer, modname, ispkg in pkgutil.iter_modules(scenes.__path__, "pyeep.scenes."):
            importlib.import_module(modname)
        for scene_cls in scenes.base.SCENES:
            scene = self.add_component(scene_cls)
            self.scenes_box.append(scene.widget)

        self.add_component(ScanAction)

        devices_menu = Gio.Menu()
        devices_menu.append("Device scan", "app.device-scan")
        devices_menu.append("Save config", "app.save-config")

        menu = pyeep.gtk.Gio.Menu()
        menu.append_submenu("Devices", devices_menu)
        self.gtk_app.set_menubar(menu)
        self.window.set_show_menubar(True)

    def ui_main(self):
        self.head.start()
        super().ui_main()


def main():
    parser = App.argparser(name="play", description="Play with nonconventional inputs and outputs")
    parser.add_argument("-i", "--iface", metavar="address", action="store", default="ws://127.0.0.1:12345",
                        help="Intiface Engine address to connect to")
    args = parser.parse_args()

    with App(args, title="Player", application_id="org.enricozini.play") as app:
        app.main()


if __name__ == "__main__":
    sys.exit(main())
