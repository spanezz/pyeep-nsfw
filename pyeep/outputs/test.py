from __future__ import annotations

# import asyncio
# from typing import Type
#
# import pyeep.outputs.base
#
# from ..component import SubprocessComponent
# from ..component.base import export
# from .power import PowerOutput, PowerOutputController
#
#
# class TestOutput(PowerOutput, SubprocessComponent):
#     """
#     Output that does nothing besides tracking the last set power value
#     """
#     def __init__(self, **kwargs):
#         kwargs.setdefault("rate", 20)
#         super().__init__(**kwargs)
#         self.proc: asyncio.subprocess.Process | None = None
#         self.read_stdin_task: asyncio.Task | None = None
#
#     @property
#     def description(self) -> str:
#         return "Test subprocess"
#
#     def get_output_controller(self) -> Type["pyeep.outputs.base.OutputController"]:
#         return PowerOutputController
#
#     @export
#     def set_power(self, power: float):
#         self.power = power
