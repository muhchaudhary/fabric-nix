from typing import Callable

import psutil
from gi.repository import GLib

from fabric.utils import exec_shell_command
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label


def invoke_repeater_threaded(
    timeout: int = 1000,
    initial_call: bool = False,
    callback: Callable | None = None,
    *args,
) -> GLib.Thread | None:
    if not callback:
        return None

    def invoke_threaded_repeater():
        ctx = GLib.MainContext()
        loop: GLib.MainLoop = GLib.MainLoop(ctx)

        source: GLib.Source = GLib.timeout_source_new(timeout)
        source.set_priority(GLib.PRIORITY_LOW)
        source.set_callback(callback, *args)
        source.attach(ctx)

        loop.run()

    callback(args) if initial_call else None

    return GLib.Thread.new(
        "fabric-config-system-temps",
        invoke_threaded_repeater,
        *args,
    )


class SystemTemps(Button):
    def __init__(self, **kwargs):
        super().__init__(name="panel-button", **kwargs)
        self.has_gpu = True if exec_shell_command("nvidia-smi") else False

        self.fan_icon = Image(
            icon_name="sensors-fan-symbolic"
            if not self.has_gpu
            else "freon-gpu-temperature-symbolic",
            icon_size=20,
        )

        self.cpu_icon = Image(icon_name="cpu-symbolic", icon_size=20)
        self.fan_speed_label = Label("-1 RPM")
        self.cpu_temp_label = Label("-1°C")

        self.add(
            Box(
                spacing=5,
                children=[
                    self.fan_icon,
                    self.fan_speed_label,
                    self.cpu_icon,
                    self.cpu_temp_label,
                ],
            )
        )

        invoke_repeater_threaded(
            timeout=1500, initial_call=True, callback=lambda *_: self.update_labels()
        )

    def update_labels(self):
        cpu_temp = round(
            (
                psutil.sensors_temperatures()["coretemp"]
                if ("coretemp" in psutil.sensors_temperatures())
                else psutil.sensors_temperatures()["k10temp"]
            )[0].current,
            1,
        )

        fan_speed = (
            psutil.sensors_fans()["thinkpad"][0].current
            if ("thinkpad" in psutil.sensors_fans())
            else None
        )

        gpu_temp = (
            exec_shell_command(
                "nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader"
            ).strip("\n")
            if self.has_gpu
            else None
        )

        self.fan_speed_label.set_label(
            f"{fan_speed} RPM"
        ) if fan_speed is not None else self.fan_speed_label.set_label(
            f"{gpu_temp}°C   "
        )

        self.cpu_temp_label.set_label(f"{cpu_temp}°C")
        return True
