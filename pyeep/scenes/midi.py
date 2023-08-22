from __future__ import annotations

from pyeep.component.base import check_hub
from pyeep.inputs.midi import MidiMessages
from pyeep.messages import Message

from .. import animation
from .base import SingleGroupScene, register
from ..output import IncreaseGroupPower


@register
class MIDIPower(SingleGroupScene):
    TITLE = "MIDIPower"

    # def build(self) -> Gtk.Expander:
    #     expander = super().build()
    #     grid = SceneGrid(max_column=self.ui_grid_columns)
    #     expander.set_child(grid)
    #     row = grid.max_row

    #     grid.attach(Gtk.Label(label="Ratio of atrial animation"), 0, row, self.ui_grid_columns - 1, 1)

    #     spinbutton = Gtk.SpinButton()
    #     spinbutton.set_adjustment(self.atrial_duration_ratio)
    #     spinbutton.set_digits(1)
    #     grid.attach(spinbutton, self.ui_grid_columns - 1, row, 1, 1)

    #     return expander

    @check_hub
    def receive(self, msg: Message):
        if not self.is_active:
            return
        match msg:
            case MidiMessages():
                for midi in msg.messages:
                    match midi.type:
                        case "note_on":
                            octave = (midi.note - 47) // 12
                            power = (midi.note - 47 - octave * 12) / 12
                            duration = 0.5 * midi.velocity / 127

                            self.send(IncreaseGroupPower(
                                group=octave + 1,
                                amount=animation.PowerPulse(
                                    duration=duration,
                                    power=power)))
