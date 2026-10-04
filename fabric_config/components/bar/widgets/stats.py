import time

import psutil
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from gi.repository import Gtk

import fabric_config.config as config
from fabric_config.services.system_stats import StatsSample
from fabric_config.widgets.popup_window_v2 import PopupWindow
from fabric_config.widgets.sparkline import Sparkline


def format_bytes(value: float, suffix: str = "") -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1000 or unit == "TB":
            precision = 0 if unit in ("B", "KB") or value >= 100 else 1
            return f"{value:.{precision}f} {unit}{suffix}"
        value /= 1000
    return ""


def format_uptime() -> str:
    seconds = int(time.time() - psutil.boot_time())
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    if days:
        return f"up {days}d {hours}h"
    return f"up {hours}h {minutes}m" if hours else f"up {minutes}m"


class StatCard(Box):
    """A titled tile: a big figure, a detail line, and a sparkline."""

    def __init__(self, title: str, icon_name: str, maximum: float | None = 100.0):
        self.value = Label("--", name="stats-card-value", h_align="start")
        self.detail = Label(
            "", name="stats-card-detail", h_align="start", ellipsization="end"
        )
        self.sparkline = Sparkline(maximum=maximum, name="stats-sparkline")
        super().__init__(
            name="stats-card",
            orientation="v",
            spacing=2,
            h_expand=True,
            children=[
                Box(
                    spacing=6,
                    children=[
                        Image(icon_name=icon_name, icon_size=14),
                        Label(title, name="stats-card-title"),
                    ],
                ),
                self.value,
                self.detail,
                self.sparkline,
            ],
        )


class SystemStatsPanel(Box):
    def __init__(self, **kwargs):
        super().__init__(name="stats-panel", orientation="v", spacing=10, **kwargs)
        self.uptime = Label("", name="stats-uptime")
        self.cpu = StatCard("CPU", "cpu-symbolic")
        self.memory = StatCard("Memory", "memory-symbolic")
        self.gpu = StatCard("GPU", "freon-gpu-temperature-symbolic")
        self.network = StatCard(
            "Network", "network-transmit-receive-symbolic", maximum=None
        )
        self.gpu.set_no_show_all(True)

        self.disk_label = Label("", name="stats-disk-label", h_align="end")
        self.disk_bar = Gtk.LevelBar(min_value=0, max_value=1)
        self.disk_bar.set_hexpand(True)
        self.disk_bar.set_valign(Gtk.Align.CENTER)
        self.disk_bar.show()

        self.process_rows = Box(orientation="v", spacing=2)
        self._process_rows: list[tuple[CenterBox, Label, Label, Label]] = []

        grid = Gtk.Grid(column_spacing=8, row_spacing=8, column_homogeneous=True)
        grid.attach(self.cpu, 0, 0, 1, 1)
        grid.attach(self.memory, 1, 0, 1, 1)
        grid.attach(self.gpu, 0, 1, 1, 1)
        grid.attach(self.network, 1, 1, 1, 1)
        grid.show()

        self.children = [
            CenterBox(
                start_children=Label("System", name="stats-title"),
                end_children=self.uptime,
            ),
            grid,
            Box(
                name="stats-disk",
                spacing=10,
                children=[
                    Image(icon_name="drive-harddisk-symbolic", icon_size=14),
                    self.disk_bar,
                    self.disk_label,
                ],
            ),
            Label("Top processes", name="stats-section", h_align="start"),
            self.process_rows,
        ]

        config.system_stats.connect("updated", lambda _, s: self.update(s))
        # fill in at once on opening, not at the next sample
        self.connect("map", lambda *_: self._update_latest())

    def _update_latest(self):
        if config.system_stats.latest is not None:
            self.update(config.system_stats.latest)

    def update(self, sample: StatsSample):
        if not self.get_mapped():
            return
        history = config.system_stats.history
        self.uptime.set_label(format_uptime())

        self.cpu.value.set_label(f"{sample.cpu:.0f}%")
        self.cpu.detail.set_label(
            f"{sample.cpu_temp:.0f}°C" if sample.cpu_temp is not None else ""
        )
        self.cpu.sparkline.set_values(history["cpu"])

        self.memory.value.set_label(f"{sample.memory_percent:.0f}%")
        self.memory.detail.set_label(
            f"{format_bytes(sample.memory_used)} of {format_bytes(sample.memory_total)}"
        )
        self.memory.sparkline.set_values(history["memory"])

        gpu = sample.gpu
        self.gpu.set_visible(gpu is not None)
        if gpu is not None:
            self.gpu.value.set_label(f"{gpu.load}%")
            self.gpu.detail.set_label(
                f"{gpu.temperature}°C · {format_bytes(gpu.memory_used)}"
                f" of {format_bytes(gpu.memory_total)}"
            )
            self.gpu.sparkline.set_values(history["gpu"])

        self.network.value.set_label(f"↓ {format_bytes(sample.net_rx, '/s')}")
        self.network.detail.set_label(f"↑ {format_bytes(sample.net_tx, '/s')}")
        self.network.sparkline.set_values(history["net_rx"])

        self.disk_bar.set_value(sample.disk_percent / 100)
        self.disk_label.set_label(
            f"{format_bytes(sample.disk_used)} of {format_bytes(sample.disk_total)}"
        )

        self._update_processes(sample)

    def _update_processes(self, sample: StatsSample):
        rows = self._process_rows
        while len(rows) < len(sample.processes):
            labels = (
                Label("", name="stats-process-name", ellipsization="end"),
                Label("", name="stats-process-memory"),
                Label("", name="stats-process-cpu"),
            )
            row = CenterBox(
                name="stats-process",
                start_children=labels[0],
                end_children=Box(spacing=12, children=[labels[1], labels[2]]),
            )
            self.process_rows.add(row)
            rows.append((row, *labels))
        for i, (row, name, memory, cpu) in enumerate(rows):
            if i >= len(sample.processes):
                row.hide()
                continue
            proc = sample.processes[i]
            name.set_label(proc.name)
            memory.set_label(format_bytes(proc.memory))
            cpu.set_label(f"{proc.cpu:.1f}%")
            row.show_all()


class SystemTemps(Button):
    def __init__(self, **kwargs):
        super().__init__(
            style_classes=["button-basic", "button-basic-props", "button-border"],
            tooltip_text="System monitor",
            on_clicked=lambda *_: SystemStatsPopup.toggle_popup(),
            **kwargs,
        )

        self.secondary_icon = Image(icon_name="sensors-fan-symbolic", icon_size=20)
        self.secondary_label = Label("--", name="stats-bar-label")
        self.cpu_temp_label = Label("--", name="stats-bar-label")

        self.add(
            Box(
                spacing=5,
                children=[
                    self.secondary_icon,
                    self.secondary_label,
                    Image(icon_name="cpu-symbolic", icon_size=20),
                    self.cpu_temp_label,
                ],
            )
        )
        config.system_stats.connect("updated", lambda _, s: self.update_labels(s))

        SystemStatsPopup.reveal_child.revealer.connect(
            "notify::reveal-child", lambda *_: self._on_popup_toggled()
        )

    def _on_popup_toggled(self):
        visible = SystemStatsPopup.popup_visible
        # the process list is only gathered while it's on screen
        config.system_stats.set_wanted(self, visible)
        if visible:
            self.add_style_class("button-basic-active")
            self.remove_style_class("button-basic")
        else:
            self.remove_style_class("button-basic-active")
            self.add_style_class("button-basic")

    def update_labels(self, sample: StatsSample):
        # a laptop shows its fan; a desktop with an NVIDIA card its GPU
        if sample.gpu is not None:
            self.secondary_icon.set_from_icon_name("freon-gpu-temperature-symbolic", 20)
            self.secondary_label.set_label(f"{sample.gpu.temperature}°C")
        elif sample.fan_rpm is not None:
            self.secondary_label.set_label(f"{sample.fan_rpm} RPM")
        else:
            self.secondary_label.set_label("--")

        cpu_temp = sample.cpu_temp
        self.cpu_temp_label.set_label(
            f"{cpu_temp:.0f}°C" if cpu_temp is not None else "--"
        )


SystemStatsPopup = PopupWindow(
    transition_duration=350,
    anchor="top-right",
    transition_type="slide-down",
    child=SystemStatsPanel(),
    enable_inhibitor=True,
)
