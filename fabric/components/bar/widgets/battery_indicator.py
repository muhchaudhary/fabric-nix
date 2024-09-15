import datetime

import config
import psutil

from fabric.core.fabricator import Fabricator
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer


class BatteryIndicator(Box):
    def __init__(self, **kwargs):
        super().__init__(v_align="center", h_align="start", **kwargs)
        if not psutil.sensors_battery():
            self.set_visible(False)
            return

        self.battery = Fabricator(
            value=[-1, -1, False],
            poll_from=lambda *args: self.poll_batt(),
            interval=1000,
        )
        self.battery.connect("changed", self.update_battery)

        self.battery_icon = Image(name="battery-icon")
        self.current_class = ""
        self.battery_percent = Label(name="battery-label")

        self.battery_percent_revealer = Revealer(
            children=self.battery_percent,
            transition_type="slide-left",
        )

        self.buttons = Button(
            name="panel-button",
        )
        self.buttons.add(  # type: ignore
            Box(
                children=[
                    self.battery_percent_revealer,
                    self.battery_icon,
                ],
            ),
        )

        self.buttons.connect(
            "clicked",
            lambda *args: self.battery_percent_revealer.set_reveal_child(
                not self.battery_percent_revealer.get_child_revealed(),
            ),
        )

        self.add(self.buttons)

    def update_battery(self, _, value):
        percent = value[0]
        secsleft = value[1]
        charging = value[2]
        self.battery_percent.set_label(str(int(round(percent))) + "%")

        self.buttons.set_tooltip_text(
            str(int(round(percent)))
            + "% "
            + str(datetime.timedelta(seconds=secsleft))
            + " left",
        ) if not charging else self.buttons.set_tooltip_text(
            str(int(round(percent))) + "% " + "Charging",
        )

        if charging:
            self.battery_icon.set_from_icon_name(
                config.battery_gtk_icon[25 * round(percent / 25)]
                + "-charging-symbolic",
                4,
            )
        else:
            self.battery_icon.set_from_icon_name(
                config.battery_gtk_icon[25 * round(percent / 25)] + "-symbolic", 4
            )
        self.battery_icon.set_pixel_size(28)
        if charging:
            if self.current_class != "charging":
                self.current_class = "charging"
                self.battery_icon.style_classes = [self.current_class]
                self.battery_percent.style_classes = [self.current_class]
        elif 30 < int(round(percent)) < 50:
            if self.current_class != "low":
                self.current_class = "low"
                self.battery_icon.style_classes = [self.current_class]
                self.battery_percent.style_classes = [self.current_class]

        elif int(round(percent)) <= 30:
            if self.current_class != "critical":
                self.current_class = "critical"
                self.battery_icon.style_classes = [self.current_class]
                self.battery_percent.style_classes = [self.current_class]
        elif self.current_class != "":
            self.current_class = ""
            self.battery_icon.style_classes = []
            self.battery_percent.style_classes = []

    def poll_batt(self):
        battery = psutil.sensors_battery()
        if battery:
            return [battery.percent, battery.secsleft, battery.power_plugged]
        else:
            return [-1, -1, False]

    def on_click(self, *args):
        self.battery_percent_revealer.set_reveal_child(
            not self.battery_percent_revealer.get_child_revealed(),
        )
