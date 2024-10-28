import psutil
from gi.repository import GLib

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label

from fabric.utils import exec_shell_command


def invoke_repeater_threaded(timeout: int, callback: callable, *args):
    def invoke_threaded_repeater():
        ctx = GLib.MainContext.new()
        loop = GLib.MainLoop.new(ctx, False)

        source = GLib.timeout_source_new(timeout)
        source.set_priority(GLib.PRIORITY_LOW)
        source.set_callback(callback, *args)
        source.attach(ctx)

        loop.run()

    GLib.Thread.new(None, invoke_threaded_repeater)


class Temps(Button):
    def __init__(self, **kwargs):
        super().__init__(name="panel-button", **kwargs)
        self.fan_icon = Image(icon_name="sensors-fan-symbolic", icon_size=20)
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
        self.update_labels()

        invoke_repeater_threaded(1500, lambda *args: self.update_labels())

    def get_gpu_temp(self):
        if self.fan_icon.get_icon_name() != "freon-gpu-temperature-symbolic":
            self.fan_icon.set_from_icon_name("freon-gpu-temperature-symbolic", 20)
        gpu_temp = exec_shell_command(
            "nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader"
        ).strip("\n")
        self.fan_speed_label.set_label(f"{gpu_temp}°C   ")
        return None

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
            else self.get_gpu_temp()
        )
        self.fan_speed_label.set_label(
            f"{fan_speed} RPM"
        ) if fan_speed is not None else None
        self.cpu_temp_label.set_label(f"{cpu_temp}°C")
        return True
