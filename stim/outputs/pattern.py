from __future__ import annotations

from typing import Any, Callable, Type

import jack
import numpy

from pyeep.component.controller import ControllerWidget
from pyeep.component.aio import AIOComponent
from pyeep.component.base import check_hub, export
from pyeep.component.jack import JackComponent
from pyeep.gtk import Gtk, Gio, GLib
from pyeep.messages import Message, Shutdown
from pyeep.midisynth import SineWave
from pyeep.outputs.base import OutputController

from ..output import PowerOutput, PowerOutputController


class Channel:
    def __init__(
            self, *,
            name: str,
            label: str,
            volume: float = 1.0,
            osc_freq: float = 1000,
            lfo_freq: float = 1,
            min_level: float = 0,
            max_level: float = 0.3):
        self.name = name
        self.label = label
        self.rate: int

        self.volume = volume

        self.osc: SineWave
        self.osc_freq = osc_freq

        self.lfo: SineWave
        self.lfo_freq = lfo_freq

        self.min_level = min_level
        self.max_level = max_level

    def set_rate(self, rate: int):
        self.rate = rate
        self.osc = SineWave(self.rate)
        self.lfo = SineWave(self.rate)

    def make_envelope(self, frames: int) -> numpy.ndarray:
        lfo = numpy.zeros(frames)
        self.lfo.wave(lfo, self.lfo_freq)

        span = self.max_level - self.min_level
        return (self.min_level + span / 2 + lfo * span / 2) * self.volume

    def synth(self, frames: int, array: numpy.ndarray):
        array.fill(0)

        if self.volume == 0.0:
            # Skip computing waveforms if volume is 0
            return

        envelope = self.make_envelope(frames)
        self.osc.synth(array, self.osc_freq, envelope)


class PatternPlayer(PowerOutput, JackComponent, AIOComponent):
    def __init__(self, frequency: float = 1000.0, **kwargs):
        super().__init__(rate=0, **kwargs)
        self.left = Channel(name="pattern_L", label="Left/A")
        self.right = Channel(name="pattern_R", label="Right/B")

    def get_output_controller(self) -> Type[OutputController]:
        return PatternOutputController

    def set_jack_client(self, jack_client: jack.Client):
        super().set_jack_client(jack_client)
        self.rate = jack_client.samplerate
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
    def setup(
            self, *,
            freq_left: float | None = None,
            freq_right: float | None = None,
            lfo_freq_left: float | None = None,
            lfo_freq_right: float | None = None,
            min_level_left: float | None = None,
            min_level_right: float | None = None,
            max_level_left: float | None = None,
            max_level_right: float | None = None):
        if freq_left is not None:
            self.left.osc_freq = freq_left
        if freq_right is not None:
            self.right.osc_freq = freq_right
        if lfo_freq_left is not None:
            self.left.lfo_freq = lfo_freq_left
        if lfo_freq_right is not None:
            self.right.lfo_freq = lfo_freq_right
        if min_level_left is not None:
            self.left.min_level = min_level_left
        if min_level_right is not None:
            self.right.min_level = min_level_right
        if max_level_left is not None:
            self.left.max_level = max_level_left
        if max_level_right is not None:
            self.right.max_level = max_level_right

    async def run(self) -> None:
        while True:
            match await self.next_message():
                case Shutdown():
                    break


class ChannelController:
    def __init__(self, channel_name: str):
        self.channel_name = channel_name

        self.freq = Gtk.Adjustment(
                value=1000.0,
                lower=100,
                upper=2000,
                step_increment=10,
                page_increment=100,
                page_size=0)

        self.lfo_freq = Gtk.Adjustment(
                value=1.0,
                lower=0,
                upper=10,
                step_increment=0.1,
                page_increment=1,
                page_size=0)

        self.min_level = Gtk.Adjustment(
                value=0.0,
                lower=0,
                upper=1,
                step_increment=0.05,
                page_increment=0.1,
                page_size=0)

        self.max_level = Gtk.Adjustment(
                value=1.0,
                lower=0,
                upper=1,
                step_increment=0.01,
                page_increment=0.1,
                page_size=0)

    def connect_value_changed(self, cb: Callable[[Gtk.Adjustement], None]):
        self.freq.connect("value_changed", cb)
        self.lfo_freq.connect("value_changed", cb)
        self.min_level.connect("value_changed", cb)
        self.max_level.connect("value_changed", cb)

    def get_config(self) -> dict[str, Any]:
        res: dict[str, Any] = {}
        for param in ("freq", "lfo_freq", "min_level", "max_level"):
            res[param] = getattr(self, param).get_value()
        return res

    def load_config(self, config: dict[str, Any]):
        for param in ("freq", "lfo_freq", "min_level", "max_level"):
            if (val := config.get(param)) is not None:
                getattr(self, param).set_value(val)

    def get_setup_kwargs(self) -> dict[str, Any]:
        return {
            f"freq_{self.channel_name}": self.freq.get_value(),
            f"lfo_freq_{self.channel_name}": self.lfo_freq.get_value(),
            f"min_level_{self.channel_name}": self.min_level.get_value(),
            f"max_level_{self.channel_name}": self.max_level.get_value(),
        }

    def attach_ui(self, cw: ControllerWidget, x: int, y: int):
        freq = Gtk.SpinButton(
            adjustment=self.freq,
            digits=1)
        cw.grid.attach(freq, x, y, 2, 1)

        lfo_freq = Gtk.SpinButton(
            adjustment=self.lfo_freq,
            digits=1)
        cw.grid.attach(lfo_freq, x, y + 1, 2, 1)

        min_level = Gtk.SpinButton(
            adjustment=self.min_level,
            digits=2)
        cw.grid.attach(min_level, x, y + 2, 2, 1)

        max_level = Gtk.SpinButton(
            adjustment=self.max_level,
            digits=2)
        cw.grid.attach(max_level, x, y + 3, 2, 1)


class PatternOutputController(PowerOutputController):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # TODO: animated targets for the various parameters
        # TODO: LFO shape left (sine, saw, square)
        # TODO: LFO shape right (sine, saw, square)

        self.left = ChannelController(channel_name="left")
        self.left.connect_value_changed(self.on_change)
        self.right = ChannelController(channel_name="right")
        self.right.connect_value_changed(self.on_change)

        self.auto_apply = Gio.SimpleAction.new_stateful(
                name=self.name.replace("_", "-") + "-auto-apply",
                parameter_type=None,
                state=GLib.Variant.new_boolean(False))
        self.hub.app.gtk_app.add_action(self.auto_apply)

        # Initialize the output with the initial UI values
        self.on_power(self.power)
        self.on_apply(None)

    def on_apply(self, button):
        self.output.setup(
            **self.left.get_setup_kwargs(),
            **self.right.get_setup_kwargs(),
        )

    def on_change(self, element):
        if not self.auto_apply.get_state().get_boolean():
            return
        self.on_apply(None)

    def build(self) -> ControllerWidget:
        cw = super().build()

        cw.grid.attach(Gtk.Label(label=self.output.left.label), 1, 4, 2, 1)
        cw.grid.attach(Gtk.Label(label=self.output.right.label), 3, 4, 2, 1)
        cw.grid.attach(Gtk.Label(label="Freq"), 0, 5, 1, 1)
        cw.grid.attach(Gtk.Label(label="LFO"), 0, 6, 1, 1)
        cw.grid.attach(Gtk.Label(label="Min"), 0, 7, 1, 1)
        cw.grid.attach(Gtk.Label(label="Max"), 0, 8, 1, 1)

        self.left.attach_ui(cw, 1, 5)
        self.right.attach_ui(cw, 3, 5)

        pulse = Gtk.Button(label="Apply")
        pulse.connect("clicked", self.on_apply)
        cw.grid.attach(pulse, 0, 9, 1, 1)

        decay = Gtk.ToggleButton(label="Auto apply")
        decay.set_action_name("app." + self.auto_apply.get_name())
        cw.grid.attach(decay, 1, 9, 1, 1)

        return cw

    @check_hub
    def load_config(self, config: dict[str, Any]):
        super().load_config(config)
        if (cfg := config.get("left")):
            self.left.load_config(cfg)
        if (cfg := config.get("right")):
            self.right.load_config(cfg)
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
