from __future__ import annotations

from pathlib import Path
from collections import deque
from typing import NamedTuple
import pickle

import numpy
from hrvanalysis import (get_frequency_domain_features,
                         get_geometrical_features, get_time_domain_features,
                         interpolate_nan_values, remove_ectopic_beats,
                         get_poincare_plot_features, remove_outliers)

from .receiver import HeartReceiver, HeartSample
import warnings

import matplotlib
matplotlib.use('GTK3Agg')  # or 'GTK3Cairo'
import matplotlib.pyplot as plt  # noqa
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg as FigureCanvas  # noqa
from pyeep.gtk import Gtk  # noqa


warnings.filterwarnings(action="ignore", message=r"nperseg = ", category=UserWarning)


class Features(NamedTuple):
    mean_nni: float
    sdnn: float
    sdsd: float
    nni_50: float
    pnni_50: float
    nni_20: float
    pnni_20: float
    rmssd: float
    median_nni: float
    range_nni: float
    cvsd: float
    cvnni: float
    mean_hr: float
    max_hr: float
    min_hr: float
    std_hr: float

    lf: float
    hf: float
    lf_hf_ratio: float
    lfnu: float
    hfnu: float
    total_power: float
    vlf: float

    triangular_index: float
    tinn: float

    sd1: float
    sd2: float
    ratio_sd2_sd1: float


class Window:
    def __init__(self, secs: int):
        self.secs = secs
        self.usecs: int = secs * 1_000_000_000
        self.samples: deque[HeartSample] = deque()
        self.feature_samples: list[HeartSample] = []
        self.feature_history: list[Features] = []

        self.marks: list[int] = []
        try:
            with open("marks.log", "rt") as fd:
                for line in fd:
                    self.marks.append(int(line))
        except FileNotFoundError:
            pass

        try:
            with open(f"{secs}.pickle", "rb") as fd:
                cache = pickle.load(fd)
                self.feature_samples = cache["samples"]
                self.feature_history = cache["features"]
            self.use_cache = True
        except FileNotFoundError:
            self.use_cache = False

        self.axes = {}
        self.plots = {}
        self.features = {
            # "mean_nni": {"ylims": (0, 200)},
            # "sdnn": {"ylims": (0, 200)},
            # "sdsd": {"ylims": (0, 200)},
            # "nni_50": {"ylims": (0, 100)},
            "pnni_50": {"ylims": (0, 100)},
            # "nni_20": {"ylims": (0, 100)},
            # "pnni_20": {"ylims": (0, 100)},
            "rmssd": {"ylims": (0, 200)},
            # "median_nni": {"ylims": (0, 200)},
            # "range_nni": {"ylims": (0, 200)},
            # "cvsd": {"ylims": (0, 200)},
            # "cvnni": {"ylims": (0, 200)},
            # "mean_hr": {"ylims": (0, 200)},
            # "max_hr": {"ylims": (0, 200)},
            # "min_hr": {"ylims": (0, 200)},
            # "std_hr": {"ylims": (0, 200)},
            # "lf": {"ylims": (0, 5000)},
            "hf": {"ylims": (0, 5000)},
            # "lf_hf_ratio": {"ylims": (0, 50)},
            # "lfnu": {"ylims": (0, 150)},
            # "hfnu": {"ylims": (0, 150)},
            # "total_power": {"ylims": (0, 5000)},
            # "vlf": {"ylims": (0, 700)},
            # "triangular_index": {"ylims": (0, 10)},
            # "tinn": {"ylims": (0, 10)},
            "sd1": {"ylims": (0, 100)},
            "sd2": {"ylims": (0, 200)},
            "ratio_sd2_sd1": {"ylims": (0, 10)},
        }

        self.figure, (self.ax_rate, *axes) = plt.subplots(len(self.features) + 1, 1, sharex=True, figsize=(10, 10))
        self.figure.suptitle(f"{secs}s")
        self.ax_rate.set_ylabel("rate")
        self.ax_rate.set_ylim(50, 150)
        self.plot_rate, = self.ax_rate.plot([])
        for name, ax in zip(self.features, axes):
            info = self.features[name]
            self.axes[name] = ax
            ax.set_ylabel(name)
            ax.set_ylim(*info["ylims"])
            plot, = ax.plot([])
            self.plots[name] = plot

        self.widget = Gtk.ScrolledWindow()
        self.canvas = FigureCanvas(self.figure)
        self.canvas.set_size_request(600, 800)
        self.widget.add_with_viewport(self.canvas)
        self.old_vlines = None

    def update_cache(self):
        if self.use_cache:
            return

        with open(f"{self.secs}.pickle", "wb") as fd:
            pickle.dump({
                "samples": self.feature_samples,
                "features": self.feature_history,
            }, fd)

    def add(self, sample: HeartSample):
        if self.use_cache:
            return

        threshold = sample.time - self.usecs
        while self.samples and self.samples[0].time < threshold:
            self.samples.popleft()
        self.samples.append(sample)

        nn = self.get_nn()
        if len(nn) < 3:
            return

        td = self.get_time_domain_features(nn)
        fd = self.get_frequency_domain_features(nn)
        gf = self.get_geometrical_features(nn)
        pf = self.get_poincare_features(nn)
        features = Features(**td, **fd, **gf, **pf)

        self.feature_samples.append(sample)
        self.feature_history.append(features)

    def get_rr(self) -> list[int]:
        res: list[int] = []
        for sample in self.samples:
            for rr in sample.rr:
                res.append(int(round(rr * 1000)))
        return res

    def get_nn(self) -> list[int]:
        rr_list = self.get_rr()
        if len(rr_list) < 3:
            return []

        # This remove outliers from signal
        rr_without_outliers = remove_outliers(rr_intervals=rr_list, low_rri=300, high_rri=2000, verbose=False)

        # This replace outliers nan values with linear interpolation
        interpolated_rr = interpolate_nan_values(rr_intervals=rr_without_outliers, interpolation_method="linear")

        # This remove ectopic beats from signal
        nn_list = remove_ectopic_beats(rr_intervals=interpolated_rr, method="malik", verbose=False)

        # This replace ectopic beats nan values with linear interpolation
        interpolated_nn = interpolate_nan_values(rr_intervals=nn_list)

        return interpolated_nn

    def get_time_domain_features(self, nn: list[int]) -> dict[str, float]:
        if len(nn) < 3:
            return {}
        return get_time_domain_features(nn)

    def get_frequency_domain_features(self, nn: list[int]) -> dict[str, float]:
        if len(nn) < 3:
            return {}
        return get_frequency_domain_features(nn)

    def get_geometrical_features(self, nn: list[int]) -> dict[str, float]:
        if len(nn) < 3:
            return {}
        return get_geometrical_features(nn)

    def get_poincare_features(self, nn: list[int]) -> dict[str, float]:
        if len(nn) < 3:
            return {}
        return get_poincare_plot_features(nn)

    def print_last(self):
        if not self.feature_samples:
            return

        s = self.feature_samples[-1]
        f = self.feature_history[-1]

        print(f"rate:{s.rate:.1f} mnni:{f.mean_nni:.1f} sdnn:{f.sdnn:.1f} sdsd:{f.sdsd:.1f} nni50:{f.nni_50:.1f}"
              f" pnni50:{f.pnni_50:.1f} nni20:{f.nni_20:.1f} pnni20:{f.pnni_20:.1f} rmssd:{f.rmssd:.1f}"
              f" mnni:{f.median_nni:.1f} rnni:{f.range_nni:.1f} cvsd:{f.cvsd:.1f} cvnni:{f.cvnni:.1f}"
              f" mhr:{f.mean_hr:.1f} maxhr:{f.max_hr:.1f} minhr:{f.min_hr:.1f} stdhr:{f.std_hr:.1f}"
              f" lf:{f.lf:.1f} hf:{f.hf:.1f} lhf:{f.lf_hf_ratio:.1f} lfnu:{f.lfnu:.1f} hfnu:{f.hfnu:.1f}")

    def update_plot(self):
        if len(self.feature_samples) < 3:
            return

        timeref = self.feature_samples[-1].time
        xdata = [(x.time - timeref) / 60_000_000_000 for x in self.feature_samples]
        rate = numpy.array([x.rate for x in self.feature_samples], dtype=float)
        self.plot_rate.set_xdata(xdata)
        self.plot_rate.set_ydata(rate)

        self.ax_rate.set_xlim(xdata[0], xdata[-1])

        if self.marks:
            xmarks = [(m - timeref) / 60_000_000_000 for m in self.marks]
            if self.old_vlines is not None:
                self.old_vlines.remove()
            self.old_vlines = self.ax_rate.vlines(
                    xmarks, 0, 1, transform=self.ax_rate.get_xaxis_transform(), colors='r')

        for name in self.features:
            ydata = numpy.array([getattr(f, name) for f in self.feature_history], dtype=float)
            self.plots[name].set_xdata(xdata)
            self.plots[name].set_ydata(ydata)

        # self.figure.canvas.draw()
        # self.figure.canvas.flush_events()
        # plt.show(block=False)
        self.canvas.draw()


# class Features(NamedTuple):
#     mean_nni: float
#     sdnn: float
#     sdsd: float
#     nni_50: float
#     pnni_50: float
#     nni_20: float
#     pnni_20: float
#     rmssd: float
#     median_nni: float
#     range_nni: float
#     cvsd: float
#     cvnni: float
#     mean_hr: float
#     max_hr: float
#     min_hr: float
#     std_hr: float
#
#     lf: float
#     hf: float
#     lf_hf_ratio: float
#     lfnu: float
#     hfnu: float
#     total_power: float
#     vlf: float
#
#     triangular_index: float
#     tinn: float


class Study(HeartReceiver):
    def __init__(self, path: Path, quiet: bool) -> None:
        super().__init__(path)
        self.quiet = quiet
        # RMSSD 10s, 30s, and 60s
        self.win_10s = Window(10)
        self.win_30s = Window(30)
        self.win_60s = Window(60)

    def add_mark(self):
        if self.samples:
            stamp = self.samples[-1].time
            with open("marks.log", "at") as fd:
                print(stamp, file=fd)
            self.win_10s.marks.append(stamp)
            self.win_30s.marks.append(stamp)
            self.win_60s.marks.append(stamp)

    async def process_sample(self, sample: HeartSample):
        import time
        start = time.time()
        self.win_10s.add(sample)
        self.win_30s.add(sample)
        self.win_60s.add(sample)

        if self.realtime:
            # self.win_10s.print_last()
            self.win_10s.update_plot()
            # self.win_30s.print_last()
            self.win_30s.update_plot()
            # self.win_60s.print_last()
            self.win_60s.update_plot()

            print("process_sample", time.time() - start)

    async def read_file(self, pathname: str):
        await super().read_file(pathname)

        self.win_10s.update_cache()
        self.win_30s.update_cache()
        self.win_60s.update_cache()

        self.win_10s.update_plot()
        self.win_30s.update_plot()
        self.win_60s.update_plot()

        # plt.show()
