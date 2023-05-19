from __future__ import annotations

import pyeep.pygame
from pyeep.app import check_hub
from pyeep.app.component import BasicActiveMixin
from pyeep.inputs.base import Input
from pyeep.messages import Message
from pyeep.pygame import pygame


class JoystickAxisMoved(Message):
    def __init__(self, *, joystick: "Joystick", axis: int, value: float, **kwargs):
        super().__init__(**kwargs)
        self.joystick = joystick
        self.axis = axis
        self.value = value

    def __str__(self):
        return super().__str__() + f"(joystick={self.joystick}, axis={self.axis}, value={self.value})"


class Joystick(BasicActiveMixin, Input, pyeep.pygame.PygameComponent):
    EVENTS = (
        pygame.JOYAXISMOTION,
        pygame.JOYBALLMOTION,
        pygame.JOYBUTTONDOWN,
        pygame.JOYBUTTONUP,
        pygame.JOYHATMOTION,
    )

    def __init__(self, *, joystick: pygame.joystick.Joystick, **kwargs):
        super().__init__(**kwargs)
        self.joystick = joystick

    @property
    def description(self) -> str:
        return self.joystick.get_name()

    @check_hub
    def pygame_event(self, event: pygame.event.Event):
        if not self.active:
            return
        if event.instance_id != self.joystick.get_instance_id():
            return
        match event.type:
            case pygame.JOYAXISMOTION:
                self.mode(event)

    def mode_default(self, event: pygame.event.Event):
        if event.axis in (4, 5):
            self.send(JoystickAxisMoved(joystick=self, axis=event.axis, value=event.value))


class Joysticks(pyeep.pygame.PygameComponent):
    EVENTS = (
        pygame.JOYDEVICEADDED,
        pygame.JOYDEVICEREMOVED
    )

    @check_hub
    def pygame_event(self, event: pygame.event.Event):
        match event.type:
            case pygame.JOYDEVICEADDED:
                joy = pygame.joystick.Joystick(event.device_index)
                # TODO: and add to inputs
                self.hub.app.add_component(Joystick, joystick=joy)

            case pygame.JOYDEVICEREMOVED:
                self.logger.warning("TODO: remove joystick #%d", event.instance_id)
