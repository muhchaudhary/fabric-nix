"""
System load and sensors, sampled once a second on a worker thread.

`config.system_stats` emits `updated(sample)` on the main thread and keeps a
minute of history per metric for sparklines (sampled less often in low-power
mode, see services/low_power.py). The top processes are only
gathered while someone asks for them (`set_wanted(owner, True)`): walking every
process each second isn't free.
"""

import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import psutil
from fabric.core.service import Service, Signal
from gi.repository import GLib
from loguru import logger

from fabric_config.utils.nvml import GpuSample, Nvml

if TYPE_CHECKING:
    from fabric_config.services.low_power import LowPower

HISTORY = 60
INTERVAL_S = 1.0
# in low-power mode, unless someone wants the top processes (the popup)
LOW_POWER_INTERVAL_S = 5.0
TOP_PROCESSES = 5


@dataclass
class ProcessSample:
    pid: int
    name: str
    cpu: float  # percent of the whole machine
    memory: int  # resident bytes


@dataclass
class StatsSample:
    cpu: float
    cpu_temp: float | None
    fan_rpm: int | None
    memory_used: int
    memory_total: int
    swap_used: int
    disk_used: int
    disk_total: int
    net_rx: float  # bytes per second
    net_tx: float
    gpu: GpuSample | None
    processes: list[ProcessSample] = field(default_factory=list)

    @property
    def memory_percent(self) -> float:
        return 100 * self.memory_used / self.memory_total if self.memory_total else 0

    @property
    def disk_percent(self) -> float:
        return 100 * self.disk_used / self.disk_total if self.disk_total else 0


class SystemStats(Service):
    @Signal
    def updated(self, sample: object) -> None: ...

    def __init__(self, low_power: "LowPower | None" = None, **kwargs):
        super().__init__(**kwargs)
        self._low_power = low_power
        # set to sample now rather than at the end of the current wait
        self._wake = threading.Event()
        self.latest: StatsSample | None = None
        self.history: dict[str, deque[float]] = {
            key: deque(maxlen=HISTORY)
            for key in ("cpu", "memory", "gpu", "net_rx", "net_tx", "cpu_temp")
        }
        self._wanted: set[object] = set()
        self._nvml = Nvml()
        self._sensors = _Sensors()
        self._processes: dict[int, psutil.Process] = {}
        self._cores = psutil.cpu_count() or 1
        threading.Thread(target=self._run, name="system-stats", daemon=True).start()

    def set_wanted(self, owner: object, wanted: bool):
        """Whether `owner` wants the top processes in each sample."""
        if wanted:
            self._wanted.add(owner)
            self._wake.set()  # don't leave an opened popup waiting 5 s
        else:
            self._wanted.discard(owner)

    def _interval(self) -> float:
        if self._low_power is not None and self._low_power.active and not self._wanted:
            return LOW_POWER_INTERVAL_S
        return INTERVAL_S

    def _run(self):
        psutil.cpu_percent()
        last_net = psutil.net_io_counters()
        last_time = time.monotonic()
        while True:
            self._wake.wait(self._interval())
            self._wake.clear()
            try:
                now = time.monotonic()
                net = psutil.net_io_counters()
                elapsed = max(now - last_time, 1e-3)
                sample = self._sample(
                    (net.bytes_recv - last_net.bytes_recv) / elapsed,
                    (net.bytes_sent - last_net.bytes_sent) / elapsed,
                )
                last_net, last_time = net, now
            except Exception as e:
                # a failing sensor mustn't end the thread
                logger.warning(f"[SystemStats] Sampling failed: {e}")
                continue
            GLib.idle_add(self._publish, sample)

    def _sample(self, net_rx: float, net_tx: float) -> StatsSample:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return StatsSample(
            cpu=psutil.cpu_percent(),
            cpu_temp=self._sensors.cpu_temp(),
            fan_rpm=self._sensors.fan_rpm(),
            memory_used=memory.total - memory.available,
            memory_total=memory.total,
            swap_used=psutil.swap_memory().used,
            disk_used=disk.used,
            disk_total=disk.total,
            net_rx=net_rx,
            net_tx=net_tx,
            gpu=self._nvml.sample(),
            processes=self._top_processes() if self._wanted else [],
        )

    def _top_processes(self) -> list[ProcessSample]:
        # cpu_percent() measures since the previous call on the same Process,
        # so keep them between samples
        seen: dict[int, psutil.Process] = {}
        samples = []
        for proc in psutil.process_iter(["name", "exe", "memory_info"]):
            proc = self._processes.get(proc.pid, proc)
            seen[proc.pid] = proc
            try:
                # of the whole machine, like the CPU figure
                cpu = proc.cpu_percent() / self._cores
                samples.append(
                    ProcessSample(
                        proc.pid,
                        _display_name(proc.info),
                        cpu,
                        proc.info["memory_info"].rss if proc.info["memory_info"] else 0,
                    )
                )
            except (psutil.Error, AttributeError, KeyError):
                continue
        self._processes = seen
        samples.sort(key=lambda p: p.cpu, reverse=True)
        return samples[:TOP_PROCESSES]

    def _publish(self, sample: StatsSample) -> bool:
        self.latest = sample
        self.history["cpu"].append(sample.cpu)
        self.history["memory"].append(sample.memory_percent)
        self.history["net_rx"].append(sample.net_rx)
        self.history["net_tx"].append(sample.net_tx)
        if sample.cpu_temp is not None:
            self.history["cpu_temp"].append(sample.cpu_temp)
        if sample.gpu is not None:
            self.history["gpu"].append(sample.gpu.load)
        self.emit("updated", sample)
        return False


def _display_name(info: dict) -> str:
    # the kernel's name stops at 15 characters, and Nix wrappers show up as
    # ".foo-wrapped"; the executable's file name reads better
    name = os.path.basename(info.get("exe") or "") or info.get("name") or "?"
    return name.removeprefix(".").removesuffix("-wrapped")


class _Sensors:
    """
    CPU temperature and fan speed straight from hwmon. psutil's
    sensors_temperatures() globs and reads every sensor file of every chip
    on each call (~3.5 ms a second here); the files wanted are found once,
    and again only if one goes away (hwmon numbering can change when a
    driver reloads).
    """

    CPU_CHIPS = ("coretemp", "k10temp", "zenpower")

    def __init__(self):
        self._temp: str | None = None
        self._fans: list[str] = []
        self._resolved = False

    def _resolve(self):
        self._resolved = True
        self._temp, self._fans = None, []
        chips: dict[str, str] = {}
        try:
            entries = sorted(os.listdir(HWMON))
        except OSError:
            return
        for entry in entries:
            path = os.path.join(HWMON, entry)
            name = _read(os.path.join(path, "name"))
            if name is not None:
                chips.setdefault(name, path)
            fans = sorted(
                f
                for f in _listdir(path)
                if f.startswith("fan") and f.endswith("_input")
            )
            if fans:
                self._fans.append(os.path.join(path, fans[0]))
        for chip in self.CPU_CHIPS:
            if chip in chips:
                temps = sorted(
                    f
                    for f in _listdir(chips[chip])
                    if f.startswith("temp") and f.endswith("_input")
                )
                if temps:
                    self._temp = os.path.join(chips[chip], temps[0])
                break

    def cpu_temp(self) -> float | None:
        if not self._resolved:
            self._resolve()
        if self._temp is None:
            return None
        value = _read(self._temp)
        if value is None:
            self._resolved = False
            return None
        return round(int(value) / 1000, 1)

    def fan_rpm(self) -> int | None:
        if not self._resolved:
            self._resolve()
        for path in self._fans:
            value = _read(path)
            if value is None:
                self._resolved = False
                return None
            if int(value):
                return int(value)
        return None


HWMON = "/sys/class/hwmon"


def _read(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read().strip()
    except (OSError, ValueError):
        return None


def _listdir(path: str) -> list[str]:
    try:
        return os.listdir(path)
    except OSError:
        return []
