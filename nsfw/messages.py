from pyeep.models.messages import Command


class RestimCommand(Command):
    #: T-Code channel name
    channel: str
    #: Value from 0 to 1
    value: float
    #: Duration in milliseconds
    duration: int = 0
