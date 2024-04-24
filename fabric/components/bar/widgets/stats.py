from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.box import Box
from fabric.widgets.label import Label
import psutil

import gi.repository.GLib as GLib


def invoke_repeater_threaded(timeout: int, callback: callable, *args):
    def invoke_threaded_repeater(timeout: int, callback: callable, *args):
        ctx = GLib.MainContext.new()
        loop = GLib.MainLoop.new(ctx, False)

        source = GLib.timeout_source_new(timeout)
        source.set_priority(GLib.PRIORITY_LOW)
        source.set_callback(callback, *args)
        source.attach(ctx)

        loop.run()

    GLib.Thread.new(None, lambda: invoke_threaded_repeater(timeout, callback, *args))


class Temps(Button):
    def __init__(self, **kwargs):
        super().__init__(name="panel-button", **kwargs)
        self.fan_icon = Image(icon_name="sensors-fan-symbolic", pixel_size=20)
        self.cpu_icon = Image(icon_name="cpu-symbolic", pixel_size=20)
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

    def update_labels(self):
        cpu_temp = psutil.sensors_temperatures()["coretemp"][0].current
        fan_speed = psutil.sensors_fans()["thinkpad"][0].current
        self.fan_speed_label.set_label(f"{fan_speed} RPM")
        self.cpu_temp_label.set_label(f"{cpu_temp}°C")
        return True
