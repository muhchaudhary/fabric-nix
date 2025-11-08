import datetime
import json
import os

import requests
from fabric.core.service import Property, Service, Signal
from fabric.utils import exec_shell_command, invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from gi.repository import GLib

from fabric_config.widgets.popup_window_v2 import PopupWindow

city = "Toronto"
country = "Canada"
api_request = (
    f"http://api.aladhan.com/v1/timingsByCity?city={city}&country={country}&method=2"
)
CACHE_DIR = GLib.get_user_cache_dir() + "/fabric"
PRAYER_TIMES_CACHE = os.path.join(CACHE_DIR, "prayer-times")
PRAYER_TIMES_FILE = os.path.join(PRAYER_TIMES_CACHE, "current_times.json")
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
if not os.path.exists(PRAYER_TIMES_CACHE):
    os.makedirs(PRAYER_TIMES_CACHE)


class PrayerTimesService(Service):
    @Signal
    def update(self, json_data: object) -> object: ...

    @Signal
    def changed(self) -> None: ...

    def __init__(self, **kwargs):
        self.prayer_info: dict = {}
        self._current_prayer = "None"
        self._next_prayer = "None"
        self._time_to_next_prayer = "None"
        super().__init__(**kwargs)
        invoke_repeater(1000 * 60, self.update_prayer_state)
        invoke_repeater(
            86400 * 1000,
            lambda: self.refresh(),
        )

    def notify_next_prayer(self):
        exec_shell_command(
            f"notify-send 'Next Prayer' 'Next prayer is {self.next_prayer}'"
        )

    def update_prayer_state(self):
        if not self.prayer_info:
            return
        now = datetime.datetime.now()
        prayer_times = {
            name: datetime.datetime.strptime(time, "%H:%M")
            for name, time in self.prayer_info.items()
        }
        prayer_names = list(prayer_times.keys())
        for i, name in enumerate(prayer_names):
            prayer_time = prayer_times[name]
            next_prayer_index = (i + 1) % len(prayer_names)
            next_prayer_name = prayer_names[next_prayer_index]
            next_prayer_time = prayer_times[next_prayer_name]
            if i + 1 == len(prayer_names):
                next_prayer_time = next_prayer_time + datetime.timedelta(days=1)

            if prayer_time.time() <= now.time() < next_prayer_time.time():
                self.current_prayer = name
                self.next_prayer = next_prayer_name
                break
        else:
            self.current_prayer = prayer_names[-1]
            self.next_prayer = prayer_names[0]

        next_prayer_time_obj = prayer_times[self.next_prayer]
        if (
            self.next_prayer == prayer_names[0]
            and self.current_prayer == prayer_names[-1]
        ):
            next_prayer_time_obj += datetime.timedelta(days=1)

        time_to_next_prayer = (
            datetime.datetime.combine(now.date(), next_prayer_time_obj.time()) - now
        )

        if time_to_next_prayer.total_seconds() < 0:
            time_to_next_prayer += datetime.timedelta(days=1)

        hours, remainder = divmod(int(time_to_next_prayer.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        self.time_to_next_prayer = f"{hours}h {minutes}m"

        if 0 <= time_to_next_prayer.total_seconds() <= 60:
            self.notify_next_prayer()
        
        return True

    @Property(object, "read-write")
    def current_prayer(self):
        return self._current_prayer

    @current_prayer.setter
    def current_prayer(self, value):
        self._current_prayer = value
        self.notify("current-prayer")

    @Property(object, "read-write")
    def next_prayer(self):
        return self._next_prayer

    @next_prayer.setter
    def next_prayer(self, value):
        self._next_prayer = value
        self.notify("next-prayer")

    @Property(object, "read-write")
    def time_to_next_prayer(self):
        return self._time_to_next_prayer

    @time_to_next_prayer.setter
    def time_to_next_prayer(self, value):
        self._time_to_next_prayer = value
        self.notify("time-to-next-prayer")

    def refresh(self):
        self._request_data() if self._refresh_needed() else self.update_times(
            self._read_json()
        )
        return self.get_property("prayer-data")

    def _request_data(self):
        try:
            response = requests.get(url=api_request)
            if response.status_code == 200:
                with open(PRAYER_TIMES_FILE, "w") as outfile:
                    json.dump(response.json()["data"], outfile, indent=4)
                self.update_times(self._read_json())
        except Exception as _:
            return

    def _read_json(self) -> dict | None:
        try:
            with open(PRAYER_TIMES_FILE, "r") as infile:
                return json.load(infile)
        except Exception as _:
            return None

    def _refresh_needed(self) -> bool:
        data = self._read_json()
        if data:
            retrived_day = data["date"]["gregorian"]["date"]
            current_day = datetime.datetime.today().strftime("%d-%m-%Y")
            return False if retrived_day == current_day else True
        return True

    @Property(object, "readable")
    def prayer_data(self) -> dict:
        return self.prayer_info

    def update_times(self, data):
        times = data["timings"]
        for prayer_name in [
            "Fajr",
            "Dhuhr",
            "Asr",
            "Maghrib",
            "Isha",
        ]:
            self.prayer_info[prayer_name] = times[prayer_name]
        self.notifier("prayer-data")
        self.emit("update", self.prayer_info)
        self.update_prayer_state()

    def notifier(self, name: str, args=None):
        self.notify(name)
        self.emit("changed")


class PrayerTimesButton(Button):
    def __init__(self, **kwargs):
        super().__init__(
            style_classes=["button-basic", "button-basic-props", "button-border"],
            **kwargs,
        )
        self.prayer_button_label = Label(label="Prayer Times", name="panel-text")
        self.prayer_button_icon = Label(label="󰥹 ", name="panel-icon")
        self.add(Box(children=[self.prayer_button_icon, self.prayer_button_label]))
        self.connect("clicked", self.on_click)
        self.prayer_service = PrayerTimesService()
        self.prayer_service.connect("notify::current-prayer", self.update_label)
        self.prayer_service.connect("notify::time-to-next-prayer", self.update_label)
        self.update_label()
        PrayerTimesPopup.reveal_child.revealer.connect(
            "notify::reveal-child",
            lambda *args: [
                self.add_style_class("button-basic-active"),
                self.remove_style_class("button-basic"),
            ]
            if PrayerTimesPopup.popup_visible
            else [
                self.remove_style_class("button-basic-active"),
                self.add_style_class("button-basic"),
            ],
        )

    def on_click(self, button, *args):
        PrayerTimesPopup.toggle_popup()

    def update_label(self, *args):
        self.prayer_button_label.set_label(
            f"{self.prayer_service.current_prayer} ({self.prayer_service.time_to_next_prayer} left)"
        )


class PrayerTimes(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="v", name="prayer-info", style_classes=["cool-border"], **kwargs
        )
        self.prayer_info_service = PrayerTimesService()

        self.prayer_labels = {
            k: (
                Label(name="prayer-info-prayer-label"),
                Label(name="prayer-info-time-label"),
            )
            for k in self.prayer_info_service.prayer_data.keys()
        }
        self.on_prayer_update(None, self.prayer_info_service.prayer_data)
        self.prayer_info_service.connect("update", self.on_prayer_update)
        self.add(Box(name="prayer-info-separator"))
        for prayer in self.prayer_labels:
            self.add(
                CenterBox(
                    name="prayer-info-row",
                    start_children=self.prayer_labels[prayer][0],
                    end_children=self.prayer_labels[prayer][1],
                )
            )
            self.add(Box(name="prayer-info-separator"))
        self.prayer_info_service.connect(
            "notify::current-prayer", self.update_prayer_label
        )
        self.update_prayer_label()

    def update_prayer_label(self, *args):
        for label in self.prayer_labels.values():
            label[0].get_parent().get_parent().get_parent().style_classes = []
        if self.prayer_info_service.current_prayer in self.prayer_labels:
            self.prayer_labels[self.prayer_info_service.current_prayer][
                0
            ].get_parent().get_parent().get_parent().style_classes = ["urgent"]

    def on_prayer_update(self, _, prayer_info):
        def time_format(time):
            d = datetime.datetime.strptime(time, "%H:%M")
            return d.strftime("  %I:%M %p")

        for info in prayer_info:
            self.prayer_labels[info][0].set_label(info)
            self.prayer_labels[info][1].set_label(time_format(prayer_info[info]))


PrayerTimesPopup = PopupWindow(
    transition_duration=350,
    anchor="top-left",
    transition_type="slide-down",
    child=PrayerTimes(),
    enable_inhibitor=True,
)
