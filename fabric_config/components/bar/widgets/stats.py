import os
from time import sleep

import psutil
from fabric import Fabricator
from fabric.utils import exec_shell_command
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label


class SystemTemps(Button):
    def __init__(self, **kwargs):
        super().__init__(
            style_classes=["button-basic", "button-basic-props", "button-border"],
            **kwargs,
        )
        self.has_gpu = os.path.exists("/dev/nvidiactl")

        self.fan_speed_label = Label("-1 RPM")
        self.cpu_temp_label = Label("-1°C")

        self.add(
            Box(
                spacing=5,
                children=[
                    Image(
                        icon_name="sensors-fan-symbolic"
                        if not self.has_gpu
                        else "freon-gpu-temperature-symbolic",
                        icon_size=20,
                    ),
                    self.fan_speed_label,
                    Image(icon_name="cpu-symbolic", icon_size=20),
                    self.cpu_temp_label,
                ],
            )
        )

        Fabricator(
            poll_from=self.get_data,
            stream=True,
            on_changed=lambda fab, data: self.update_labels(data),
        )

    def get_data(self, fab: Fabricator):
        while True:
            yield {
                "cpu-temp": self._read_cpu_temp(),
                "fan-speed": self._read_fan_speed(),
                "gpu-temp": exec_shell_command(
                    "nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader"
                ).strip("\n")  # type: ignore
                if self.has_gpu
                else None,
            }
            sleep(1)

    @staticmethod
    def _read_cpu_temp() -> float | None:
        # a missing sensor must not raise: that would end this polling thread
        temps = psutil.sensors_temperatures()
        for chip in ("coretemp", "k10temp"):
            if temps.get(chip):
                return round(temps[chip][0].current, 1)
        return None

    @staticmethod
    def _read_fan_speed() -> int | None:
        fans = psutil.sensors_fans()
        return fans["thinkpad"][0].current if fans.get("thinkpad") else None

    def update_labels(self, data):
        if data["fan-speed"] is not None:
            self.fan_speed_label.set_label(f"{data['fan-speed']} RPM")
        elif data["gpu-temp"] is not None:
            self.fan_speed_label.set_label(f"{data['gpu-temp']}°C   ")
        else:
            self.fan_speed_label.set_label("--")

        cpu_temp = data["cpu-temp"]
        self.cpu_temp_label.set_label(f"{cpu_temp}°C" if cpu_temp is not None else "--")
        return True
