from __future__ import annotations

import sys
from collections import deque
from pathlib import Path
from typing import Callable, Optional

import numpy
import scipy.stats

from .receiver import HeartReceiver, HeartSample


class Slope:
    def __init__(self, samples: list[HeartSample], slope: float):
        self.samples = list(samples)
        self.min_slope: float = slope
        self.max_slope: float = slope
        self.last_slope: float = slope
        self.min_rate: float = min(s.rate for s in samples)
        self.max_rate: float = max(s.rate for s in samples)

    @property
    def duration(self) -> float:
        return (self.samples[-1].time - self.samples[0].time) / 1_000_000_000

    @property
    def height(self) -> float:
        return self.max_rate - self.min_rate

    @property
    def mid_rate(self) -> float:
        return (self.min_rate + self.max_rate) / 2.0

    def extend(self, samples: list[HeartSample], slope: float):
        new_samples = [s for s in samples if s.time > self.samples[-1].time]
        self.samples.extend(new_samples)
        for s in new_samples:
            if s.rate < self.min_rate:
                self.min_rate = s.rate
            if s.rate > self.max_rate:
                self.max_rate = s.rate
        if slope < self.min_slope:
            self.min_slope = slope
        if slope > self.max_slope:
            self.max_slope = slope
        self.last_slope = slope


class Slopes:
    def __init__(self, min_slope_duration: float, min_slope_height: float):
        self.slopes: list[Slope] = []
        self.current: Optional[Slope] = None
        self.min_slope_duration = min_slope_duration
        self.min_slope_height = min_slope_height

    def check(self, window_samples: list[HeartSample], slope: float, above_threshold: bool) -> int:
        if above_threshold:
            if self.current is None:
                self.current = Slope(window_samples, slope)
                return 1
            else:
                self.current.extend(window_samples, slope)
                return 2
        else:
            if (self.current
                    and self.current.duration > self.min_slope_duration
                    and self.current.height > self.min_slope_height):
                self.slopes.append(self.current)
                self.current = None
                return 3
            else:
                self.current = None
                return 0


class Window:
    def __init__(
            self,
            name: str,
            width_seconds: float):
        self.name = name
        self.width_seconds = width_seconds
        self.climbs = Slopes(min_slope_duration=3.0, min_slope_height=6)
        self.falls = Slopes(min_slope_duration=3.0, min_slope_height=6)
        self.coasts = Slopes(min_slope_duration=8, min_slope_height=0)
        self.last_slope: float = 0.0
        self.last_variance: float = 0.0
        self.slope_climbing: bool = False
        self.summary: str = ' '

    def sample(self, samples: list[HeartSample]):
        last_time = samples[-1].time
        threshold = last_time - self.width_seconds * 1_000_000_000
        window_samples = [s for s in samples if s.time >= threshold]
        if len(window_samples) <= 1:
            return
        data = numpy.array([
            [(s.time - last_time) / 1_000_000_000 for s in window_samples],
            [s.rate for s in window_samples]])
        reg = scipy.stats.linregress(data)
        variance = numpy.var(data[1, :])
        c = self.climbs.check(window_samples, reg.slope, reg.slope > 0.3)
        f = self.falls.check(window_samples, reg.slope, reg.slope < -0.3)
        q = self.coasts.check(window_samples, reg.slope, variance < 1.0 or (reg.slope < 0.1 and reg.slope > -0.1))
        # q = self.coasts.check(window_samples, reg.slope, variance < 1.0)
        self.summary = ".↑↗⇥"[c] + ".↓↘⇥"[f] + ".↦-↤"[q]
        self.slope_climbing = reg.slope > 0 and reg.slope >= self.last_slope
        if self.slope_climbing:
            self.summary += "↺"
        else:
            self.summary += " "
        self.last_slope = reg.slope
        self.last_variance = variance


class HSpan:
    def __init__(self, sample: HeartSample):
        self.min_sample = sample
        self.max_sample = sample

    def add(self, sample: HeartSample):
        self.max_sample = sample


class Excitement(HeartReceiver):
    def __init__(self, *, path: Path, quiet: bool) -> None:
        super().__init__(path=path)
        self.quiet = quiet
        self.history: deque[HeartSample] = deque(maxlen=20)
        self.window = Window("10s", 10)
        self.hspans: list[HSpan] = []
        self.current_hspan: Optional[HSpan] = None
        self.interesting = False
        self.on_sample: Optional[Callable[[], None]] = None
        self.last_sample: HeartSample | None = None

    def shutdown(self):
        self.shutting_down = True

    @property
    def last_rate(self) -> float:
        if self.history:
            return self.history[-1].rate
        else:
            return 0.0

    @property
    def last_slope(self) -> float:
        return self.window.last_slope

    @property
    def slope_climbing(self) -> float:
        return self.window.slope_climbing

    @property
    def climbing(self) -> bool:
        return self.window.climbs.current is not None

    @property
    def falling(self) -> bool:
        return self.window.falls.current is not None

    @property
    def coasting(self) -> bool:
        return self.window.coasts.current is not None

    @property
    def current_slope(self) -> str:
        """
        Return "climb", "fall", "coast", or "none" depending on what is the
        most recent current slope
        """
        max_start: float | None = None

        res = "none"

        if (slope := self.window.climbs.current) is not None:
            if max_start is None or max_start < slope.samples[0].time:
                max_start = slope.samples[0].time
                res = "climb"

        if (slope := self.window.coasts.current) is not None:
            if max_start is None or max_start < slope.samples[0].time:
                max_start = slope.samples[0].time
                res = "coast"

        if (slope := self.window.falls.current) is not None:
            if max_start is None or max_start < slope.samples[0].time:
                max_start = slope.samples[0].time
                res = "fall"

        return res

    @property
    def state(self):
        if self.interesting:
            return "excite"
        elif (state := self.current_slope) == "none":
            return "coast"
        else:
            return state

    def check_history(self):
        samples = list(self.history)
        if len(samples) < 2:
            return
        desc = ""
        self.window.sample(samples)
        desc += self.window.summary

        # long_samples = data[:, data[0, :] > -15]
        prev_rate = samples[-2].rate
        cur_rate = samples[-1].rate

        last_fall: Optional[Slope] = self.window.falls.slopes[-1] if self.window.falls.slopes else None
        last_coast: Optional[Slope] = self.window.coasts.slopes[-1] if self.window.coasts.slopes else None
        self.interesting = False
        if self.window.slope_climbing and (last_fall or last_coast):
            if last_fall is None:
                threshold = last_coast.mid_rate + 1
            elif last_coast is None:
                threshold = last_fall.min_rate
            elif last_coast.samples[-1].time < last_fall.samples[-1].time:
                threshold = last_fall.min_rate
            else:
                threshold = last_coast.mid_rate
            if cur_rate > prev_rate and cur_rate >= threshold and self.window.falls.current is None:
                self.interesting = True

        if self.interesting:
            desc += "!"
            if self.current_hspan is None:
                self.current_hspan = HSpan(samples[-1])
            else:
                self.current_hspan.add(samples[-1])
        elif self.current_hspan is not None:
            self.hspans.append(self.current_hspan)
            self.current_hspan = None

        # TODO: detect when the slopes are maximum and store the samples, to
        # keep a reference of the span of the last climb(s)

        if not self.quiet:
            self.print_status(desc)

    def print_status(self, desc: str):
        print("History", [f"{s.rate:3.0f}" for s in self.history], end=" ")
        w = self.window
        print(f"{w.name}: {w.last_slope:+.04f}: {desc} {self.state}")
        sys.stdout.flush()

    async def process_sample(self, sample: HeartSample):
        self.last_sample = sample
        self.history.append(sample)
        self.check_history()
        if self.on_sample:
            self.on_sample()

    async def read_file(self, pathname: str):
        await super().read_file(pathname)
        all_samples = self.samples

        import matplotlib.pyplot as plt
        self.figure, self.ax = plt.subplots(figsize=(8, 6))

        last_time = all_samples[-1].time
        time_scale = 60_000_000_000

        def graph_x(sample: HeartSample) -> float:
            return (sample.time - last_time) / time_scale

        plot_x = numpy.array([graph_x(s) for s in all_samples])

        # plot all_samples
        plot_y = numpy.array([s.rate for s in all_samples])
        self.ax.set_ylim([numpy.nanmin(plot_y) - 10, numpy.nanmax(plot_y) + 1])
        self.ax.plot(plot_x, plot_y)

        # Highlight slopes for all window sizes (colored vertical bar from the slope starting point)
        for slope in self.window.climbs.slopes:
            self.ax.errorbar(
                    graph_x(slope.samples[0]), slope.min_rate,
                    lolims=True, yerr=slope.max_rate - slope.min_rate,
                    ecolor="red")
            self.ax.errorbar(
                    graph_x(slope.samples[0]), slope.min_rate,
                    xlolims=True, xerr=(slope.samples[-1].time - slope.samples[0].time) / time_scale,
                    ecolor="red")
        for slope in self.window.falls.slopes:
            self.ax.errorbar(
                    graph_x(slope.samples[0]), slope.max_rate,
                    uplims=True, yerr=slope.max_rate - slope.min_rate,
                    ecolor="blue")
            self.ax.errorbar(
                    graph_x(slope.samples[0]), slope.max_rate,
                    xlolims=True, xerr=(slope.samples[-1].time - slope.samples[0].time) / time_scale,
                    ecolor="blue")
        for slope in self.window.coasts.slopes:
            self.ax.errorbar(
                    graph_x(slope.samples[0]), slope.mid_rate,
                    yerr=(slope.max_rate - slope.min_rate) / 2,
                    ecolor="green")
            self.ax.errorbar(
                    graph_x(slope.samples[0]), slope.mid_rate,
                    xlolims=True, xerr=(slope.samples[-1].time - slope.samples[0].time) / time_scale,
                    ecolor="green")

        # Plot areas of the graph where the last sample was triggering '!'
        for hspan in self.hspans:
            self.ax.axvspan(graph_x(hspan.min_sample), graph_x(hspan.max_sample), color="crimson", alpha=0.3)

        plt.show()


# Alternative implementation that doesn't seem as accurate
#
# class Heart:
#     def __init__(self, socket: str):
#         self.socket = socket
#         self.last_sample: HeartSample | None = None
#         self.last_window: deque[HeartSample] = deque(maxlen=10)
#         self.improvised_delta: float = 0
#         self.shutting_down: bool = False
#         self.state: str = "coast"
#
#     async def read_socket(self):
#         # Read heart beats from https://www.enricozini.org/blog/2023/debian/monitoring-a-heart-rate-monitor/
#         reader, writer = await asyncio.open_unix_connection(self.socket)
#
#         # Skip the initial line with recent heartbeat history
#         initial = json.loads(await reader.readline())
#         for sample in (HeartSample(*s) for s in initial["last"]):
#             self.last_window.append(sample)
#
#         while not self.shutting_down and (line := await reader.readline()):
#             self.last_sample = HeartSample(*json.loads(line))
#             self.on_sample()
#             self.last_window.append(self.last_sample)
#
#     def on_sample0(self):
#         # Use mean and variance to detect when the next sample is an outlier
#         # print("SAMPLE", self.last_sample)
#         if len(self.last_window) > 3:
#             samples = [x.rate for x in self.last_window]
#             mean = statistics.mean(samples)
#             variance = statistics.variance(samples)
#             if self.last_sample.rate > mean + variance:
#                 self.improvised_delta = self.last_sample.rate - mean - variance
#             elif self.last_sample.rate < mean - variance:
#                 self.improvised_delta = -(mean - variance - self.last_sample.rate)
#             else:
#                 self.improvised_delta = 0.0
#             # print("Improvised delta:", self.improvised_delta)
#
#         if self.improvised_delta > 2:
#             self.state = "excite"
#         elif self.improvised_delta > 0.5:
#             self.state = "climb"
#         elif self.improvised_delta < -0.5:
#             self.state = "fall"
#         else:
#             self.state = "coast"
#
#     def on_sample(self):
#         # print("SAMPLE", self.last_sample)
#         if len(self.last_window) > 3:
#             first_sample = self.last_window[0]
#             samples_x = [(x.time - first_sample.time) / 1_000_000_000 for x in self.last_window]
#             samples_y = [x.rate for x in self.last_window]
#             slope, intercept = statistics.linear_regression(samples_x, samples_y)
#             predicted = slope * (self.last_sample.time - first_sample.time) / 1_000_000_000 + intercept
#             difference = self.last_sample.rate - predicted
#             # mean = statistics.mean(self.last_window)
#             # variance = statistics.variance(self.last_window)
#             # if self.last_sample.rate > mean + variance:
#             #     self.improvised_delta = self.last_sample.rate - mean - variance
#             # elif self.last_sample.rate < mean - variance:
#             #     self.improvised_delta = -(mean - variance - self.last_sample.rate)
#             # else:
#             #     self.improvised_delta = 0.0
#             # # print("Improvised delta:", self.improvised_delta)
#
#             if difference > 2:
#                 self.state = "excite"
#             elif difference >= 1:
#                 self.state = "climb"
#             elif difference <= -1:
#                 self.state = "fall"
#             else:
#                 self.state = "coast"
#
#             print(f"{self.last_sample.rate} {predicted=:.1f} {slope=:.1f}"
#                   f" {intercept=:.1f} {difference=:.1f} {self.state}")
#
#             # if self.improvised_delta > 2:
#             #     self.state = "excite"
#             # elif self.improvised_delta > 0.5:
#             #     self.state = "climb"
#             # elif self.improvised_delta < -0.5:
#             #     self.state = "fall"
#             # else:
#             #     self.state = "coast"
#
#         else:
#             self.state = "coast"
