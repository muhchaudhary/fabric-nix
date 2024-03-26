import psutil
import datetime
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.revealer import Revealer
from fabric.utils.fabricator import Fabricate

icons = {
    0: "󱃍",
    10: "󰁺",
    20: "󰁻",
    30: "󰁼",
    40: "󰁽",
    50: "󰁾",
    60: "󰁿",
    70: "󰂀",
    80: "󰂁",
    90: "󰂂",
    100: "󰁹",
}

charging_icons = {
    0: "󰢟",
    10: "󰢜",
    20: "󰂆",
    30: "󰂇",
    40: "󰂈",
    50: "󰢝",
    60: "󰂉",
    70: "󰢞",
    80: "󰂊",
    90: "󰂋",
    100: "󰂅",
}


class BatteryIndicator(Box):
    def __init__(self, **kwargs):
        super().__init__(v_align="center", h_align="start", **kwargs)
        self.battery = Fabricate(
            value=[-1, -1, False],
            poll_from=lambda *args: self.poll_batt(),
            interval=1000,
        )
        self.battery.connect("changed", self.update_battery)

        self.battery_icon = Label(name="battery-icon")

        self.battery_percent = Label(name="battery-label")

        self.battery_percent_revealer = Revealer(
            children=self.battery_percent,
            transition_type="slide-left",
        )

        self.buttons = Button(
            name="panel-button",
        )
        self.buttons.add( # type: ignore
            Box(
                children=[self.battery_percent_revealer,
                          self.battery_icon,
                          ],
            )
        )

        self.buttons.connect(
            "clicked",
            lambda *args: self.battery_percent_revealer.set_reveal_child(
                not self.battery_percent_revealer.get_child_revealed()
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
            + " left"
        ) if not charging else self.buttons.set_tooltip_text(
            str(int(round(percent))) + "% " + "Charging"
        )

        if charging:
            self.battery_icon.set_label(charging_icons[int(round(percent, -1))])
        else:
            self.battery_icon.set_label(icons[int(round(percent, -1))])

        if charging:
            self.battery_icon.set_name("battery-icon-charging")
            self.battery_percent.set_name("battery-label-charging")
        elif 30 < int(round(percent)) < 50:
            self.battery_icon.set_name("battery-icon-low")
            self.battery_percent.set_name("battery-label-low")
        elif int(round(percent)) <= 30:
            self.battery_icon.set_name("battery-icon-critical")
            self.battery_percent.set_name("battery-label-critical")
        else:
            self.battery_icon.set_name("battery-icon")
            self.battery_percent.set_name("battery-label")

    def poll_batt(self):
        battery = psutil.sensors_battery()
        if battery:
            return [battery.percent, battery.secsleft, battery.power_plugged]
        else:
            return [-1, -1, False]

    def on_click(self, *args):
        self.battery_percent_revealer.set_reveal_child(
            not self.battery_percent_revealer.get_child_revealed()
        )
