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
        super().__init__(style_classes=["button-basic", "button-basic-props", "button-border"], **kwargs)
        self.has_gpu = True if exec_shell_command("nvidia-smi") else False

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
                "cpu-temp": round(
                    (
                        psutil.sensors_temperatures()["coretemp"]
                        if ("coretemp" in psutil.sensors_temperatures())
                        else psutil.sensors_temperatures()["k10temp"]
                    )[0].current,
                    1,
                ),
                "fan-speed": psutil.sensors_fans()["thinkpad"][0].current
                if ("thinkpad" in psutil.sensors_fans())
                else None,
                "gpu-temp": exec_shell_command(
                    "nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader"
                ).strip("\n")  # type: ignore
                if self.has_gpu
                else None,
            }
            sleep(1)

    def update_labels(self, data):
        self.fan_speed_label.set_label(f"{data["fan-speed"]} RPM") if data[
            "fan-speed"
        ] is not None else self.fan_speed_label.set_label(f"{data["gpu-temp"]}°C   ")

        self.cpu_temp_label.set_label(f"{data["cpu-temp"]}°C")
        return True
