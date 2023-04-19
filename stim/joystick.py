from __future__ import annotations

import pyeep.pygame
from pyeep.app import Message, Shutdown, check_hub
from pyeep.pygame import pygame

from .inputs import Input, InputSetActive


class Joystick(Input, pyeep.pygame.PygameComponent):
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
        self.active = False

    @pyeep.aio.export
    def is_active(self) -> bool:
        return self.active

    @property
    def description(self) -> str:
        return "Joystick"

    @check_hub
    def pygame_event(self, event: pygame.event.Event):
        if event.instance_id == self.joystick.get_instance_id():
            print("JEV", event)


class Joysticks(Input, pyeep.pygame.PygameComponent):
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
