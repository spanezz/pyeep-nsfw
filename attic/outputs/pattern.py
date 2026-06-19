from __future__ import annotations

from typing import Any, Type

import jack
import numpy

from pyeep.component.controller import ControllerWidget
from pyeep.component.aio import AIOComponent
from pyeep.component.base import check_hub, export
from pyeep.component.jack import JackComponent
from pyeep.gtk import Gtk, Gio, GLib, GObject
from pyeep.messages.message import Message
from pyeep.messages.component import Shutdown
from pyeep.synth import Wave, SineWave, SawWave
from pyeep.outputs.base import BaseOutputController

from .power import PowerOutput


class Channel:
    def __init__(
            self, *,
            name: str,
            label: str,
            volume: float = 1.0,
            osc_freq: float = 1000,
            lfo_freq: float = 1,
            lfo_shape: str = "sine",
            min_level: float = 0,
            max_level: float = 0.3):
        self.name = name
        self.label = label
        self.rate: int | None = None

        self.volume = volume

        self.osc: Wave | None = None
        self.osc_freq = osc_freq

        self.lfo: Wave | None = None
        self.lfo_freq = lfo_freq
        self.lfo_shape = lfo_shape

        self.min_level = min_level
        self.max_level = max_level

    def set_rate(self, rate: int):
        self.rate = rate
        self.osc = SineWave(self.rate)
        self.setup()

    def make_envelope(self, frames: int) -> numpy.ndarray:
        lfo = numpy.zeros(frames)
        self.lfo.wave(lfo, self.lfo_freq)

        span = self.max_level - self.min_level
        return (self.min_level + span / 2 + lfo * span / 2) * self.volume

    def synth(self, frames: int, array: numpy.ndarray):
        array.fill(0)

        if self.volume == 0.0 or self.osc is None or self.lfo is None:
            # Skip computing waveforms if volume is 0
            return

        envelope = self.make_envelope(frames)
        self.osc.synth(array, self.osc_freq, envelope)

    def setup(
            self, *,
            freq: float | None = None,
            lfo_freq: float | None = None,
            lfo_shape: str | None = None,
            min_level: float | None = None,
            max_level: float | None = None):
        if freq is not None:
            self.osc_freq = freq
        if lfo_freq is not None:
            self.lfo_freq = lfo_freq
        if min_level is not None:
            self.min_level = min_level
        if max_level is not None:
            self.max_level = max_level

        # Hack to use setup at set_rate time to initialize the right LFO
        # oscillators
        if self.lfo is None and lfo_shape is None:
            lfo_shape = self.lfo_shape

        if lfo_shape is not None:
            if self.lfo is None or self.lfo_shape != lfo_shape:
                self.lfo_shape = lfo_shape
                match lfo_shape:
                    case "sine":
                        self.lfo = SineWave(self.rate)
                    case "saw":
                        self.lfo = SawWave(self.rate)


class PatternPlayer(PowerOutput, JackComponent, AIOComponent):
    def __init__(self, frequency: float = 1000.0, **kwargs):
        super().__init__(rate=0, **kwargs)
        self.left = Channel(name="pattern_L", label="Left/A")
        self.right = Channel(name="pattern_R", label="Right/B")

    def get_output_controller(self, **kwargs) -> Type[BaseOutputController]:
        base = super().get_output_controller(**kwargs)
        return type("PatternOutputController", (PatternOutputController, base), {})

    def set_jack_client(self, jack_client: jack.Client):
        super().set_jack_client(jack_client)
        self.set_rate(jack_client.samplerate)
        self.left.set_rate(self.rate)
        self.right.set_rate(self.rate)
        self.outport_l = self.jack_client.outports.register('pattern_L')
        # print(self.jack_client.inports)
        # print(self.jack_client.outports)
        # print(self.jack_client.get_ports(name_pattern="Built-in Audio Analog Stereo:", is_audio=True, is_input=True))
        self.outport_r = self.jack_client.outports.register('pattern_R')
        # TODO: autoconnect to previously connected ports
        self.outport_l.connect("Built-in Audio Analog Stereo:playback_FL")
        self.outport_r.connect("Built-in Audio Analog Stereo:playback_FR")

    def jack_process(self, frames: int) -> None:
        self.left.synth(frames, self.outport_l.get_array())
        self.right.synth(frames, self.outport_r.get_array())

    @export
    def set_power(self, power: float):
        self.left.volume = power
        self.right.volume = power

    @export
    def setup(self, *, left: dict[str, Any], right: dict[str, Any]):
        self.left.setup(**left)
        self.right.setup(**right)

    async def run(self) -> None:
        while True:
            match await self.next_message():
                case Shutdown():
                    break


class ChannelController(GObject.Object):
    def __init__(self, channel_name: str):
        super().__init__()
        self.channel_name = channel_name

        self.freq = Gtk.Adjustment(
                value=1000.0,
                lower=100,
                upper=2000,
                step_increment=10,
                page_increment=100,
                page_size=0)
        self.freq.connect("value_changed", self.on_adjust_changed)

        self.lfo_freq = Gtk.Adjustment(
                value=1.0,
                lower=0,
                upper=10,
                step_increment=0.1,
                page_increment=1,
                page_size=0)
        self.lfo_freq.connect("value_changed", self.on_adjust_changed)

        lfo_shapes = Gtk.ListStore(str, str)
        lfo_shapes.append(["sine", "Sine"])
        lfo_shapes.append(["saw", "Saw"])

        self.lfo_shape = Gtk.ComboBox(model=lfo_shapes)
        self.lfo_shape.set_id_column(0)
        renderer = Gtk.CellRendererText()
        self.lfo_shape.pack_start(renderer, True)
        self.lfo_shape.add_attribute(renderer, "text", 1)
        self.lfo_shape.set_active_id("sine")
        self.lfo_shape.connect("changed", self.on_lfo_shape_changed)

        self.min_level = Gtk.Adjustment(
                value=0.0,
                lower=0,
                upper=1,
                step_increment=0.05,
                page_increment=0.1,
                page_size=0)
        self.min_level.connect("value_changed", self.on_adjust_changed)

        self.max_level = Gtk.Adjustment(
                value=1.0,
                lower=0,
                upper=1,
                step_increment=0.01,
                page_increment=0.1,
                page_size=0)
        self.max_level.connect("value_changed", self.on_adjust_changed)

    @GObject.Signal
    def changed(self):
        pass

    def on_adjust_changed(self, adj: Gtk.Adjustment):
        self.emit("changed")

    def on_lfo_shape_changed(self, combo: Gtk.ComboBox):
        self.emit("changed")

    def _get_lfo_shape(self) -> str | None:
        tree_iter = self.lfo_shape.get_active_iter()
        if tree_iter is None:
            return None
        model = self.lfo_shape.get_model()
        mode = model[tree_iter][0]
        return mode

    def get_config(self) -> dict[str, Any]:
        res: dict[str, Any] = {}
        for param in ("freq", "lfo_freq", "min_level", "max_level"):
            res[param] = getattr(self, param).get_value()
        res["lfo_shape"] = self._get_lfo_shape()
        return res

    def load_config(self, config: dict[str, Any]):
        for param in ("freq", "lfo_freq", "min_level", "max_level"):
            if (val := config.get(param)) is not None:
                getattr(self, param).set_value(val)

        if (val := config.get("lfo_shape")) is not None:
            self.lfo_shape.set_active_id(val)

    def get_setup_kwargs(self) -> dict[str, Any]:
        return self.get_config()

    def attach_ui(self, grid: Gtk.Grid, x: int, y: int):
        freq = Gtk.SpinButton(
            adjustment=self.freq,
            digits=1)
        grid.attach(freq, x, y, 2, 1)

        lfo_freq = Gtk.SpinButton(
            adjustment=self.lfo_freq,
            digits=1)
        grid.attach(lfo_freq, x, y + 1, 2, 1)

        grid.attach(self.lfo_shape, x, y + 2, 2, 1)

        min_level = Gtk.SpinButton(
            adjustment=self.min_level,
            digits=2)
        grid.attach(min_level, x, y + 3, 2, 1)

        max_level = Gtk.SpinButton(
            adjustment=self.max_level,
            digits=2)
        grid.attach(max_level, x, y + 4, 2, 1)


class PatternOutputController(BaseOutputController):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.left = ChannelController(channel_name="left")
        self.left.connect("changed", self.on_channel_changed)
        self.right = ChannelController(channel_name="right")
        self.right.connect("changed", self.on_channel_changed)
        self.auto_apply = Gio.SimpleAction.new_stateful(
                name=self.name.replace("_", "-") + "-auto-apply",
                parameter_type=None,
                state=GLib.Variant.new_boolean(False))
        self.hub.app.gtk_app.add_action(self.auto_apply)

        # TODO: animated ramp targets for the various parameters

    def on_apply(self, button):
        self.output.setup(
            left=self.left.get_setup_kwargs(),
            right=self.right.get_setup_kwargs(),
        )

    def on_channel_changed(self, channel: ChannelController):
        if not self.auto_apply.get_state().get_boolean():
            return
        self.on_apply(None)

    def build(self) -> ControllerWidget:
        cw = super().build()

        grid = Gtk.Grid()
        grid.set_hexpand(True)
        cw.box.append(grid)

        grid.attach(Gtk.Label(label=self.output.left.label), 1, 0, 2, 1)
        grid.attach(Gtk.Label(label=self.output.right.label), 3, 0, 2, 1)
        grid.attach(Gtk.Label(label="Freq"), 0, 1, 1, 1)
        grid.attach(Gtk.Label(label="LFO"), 0, 2, 1, 1)
        grid.attach(Gtk.Label(label="Shape"), 0, 3, 1, 1)
        grid.attach(Gtk.Label(label="Min"), 0, 4, 1, 1)
        grid.attach(Gtk.Label(label="Max"), 0, 5, 1, 1)

        self.left.attach_ui(grid, 1, 1)
        self.right.attach_ui(grid, 3, 1)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        buttons.set_hexpand(True)
        cw.box.append(buttons)

        apply = Gtk.Button(label="Apply")
        apply.connect("clicked", self.on_apply)
        buttons.append(apply)

        autoapply = Gtk.ToggleButton(label="Auto apply")
        autoapply.set_action_name("app." + self.auto_apply.get_name())
        buttons.append(autoapply)

        return cw

    @check_hub
    def load_config(self, config: dict[str, Any]):
        super().load_config(config)
        if (cfg := config.get("left")):
            self.left.load_config(cfg)
        if (cfg := config.get("right")):
            self.right.load_config(cfg)
        self.on_power(self.power)
        self.on_apply(None)

    @check_hub
    def get_config(self) -> dict[str, Any]:
        res = super().get_config()
        res["left"] = self.left.get_config()
        res["right"] = self.right.get_config()
        return res

    @check_hub
    def receive(self, msg: Message):
        match msg:
            case _:
                super().receive(msg)
