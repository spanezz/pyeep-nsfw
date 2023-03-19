from __future__ import annotations

import queue

import pyeep.gtk
from . import lovense


class LovenseCommandLogView(pyeep.gtk.LogView):
    def __init__(self, max_lines: int = 10):
        super().__init__(max_lines)
        self.queue: queue.Queue[str] = queue.Queue()

    def attach(self, toy: lovense.Lovense):
        toy.notify_command = self.on_command

    def on_command(self, cmd):
        # Executed in the aio thread
        self.queue.put(cmd)
        pyeep.gtk.GLib.idle_add(self.process_queues)

    def process_queues(self):
        while not self.queue.empty():
            self.append(self.queue.get())
        return False
