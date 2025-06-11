import datetime
import json
import os

import requests
from fabric.core.service import Property, Service, Signal
from fabric.utils import invoke_repeater
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
        super().__init__(**kwargs)
        invoke_repeater(
            12 * 60 * 60 * 60,
            lambda: self.refresh(),
        )

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
        for prayer_name in times:
            self.prayer_info[prayer_name] = times[prayer_name]
        self.notifier("prayer-data")
        self.update(self.prayer_info)

    def notifier(self, name: str, args=None):
        self.notify(name)
        self.changed()


class PrayerTimesButton(Button):
    def __init__(self, **kwargs):
        super().__init__(style_classes=["button-basic", "button-basic-props"], **kwargs)
        self.prayer_button_label = Label(label="Prayer Times", name="panel-text")
        self.prayer_button_icon = Label(label="󰥹 ", name="panel-icon")
        self.add(Box(children=[self.prayer_button_icon, self.prayer_button_label]))
        self.connect("clicked", self.on_click)
        PrayerTimesPopup.reveal_child.revealer.connect(
            "notify::reveal-child",
            lambda *args: [self.add_style_class(
                "button-basic-active"
            ), 
              self.remove_style_class(
                "button-basic"
            )
            ]
            if PrayerTimesPopup.popup_visible
            else [self.remove_style_class(
                "button-basic-active"
            ), 
            self.add_style_class(
                "button-basic"
            )
            ],
        )

    def on_click(self, button, *args):
        PrayerTimesPopup.toggle_popup()


class PrayerTimes(Box):
    def __init__(self, **kwargs):
        super().__init__(orientation="v", name="prayer-info", **kwargs)
        self.prayer_info_service = PrayerTimesService()

        self.prayer_labels = {
            k: (Label(name="prayer-info-prayer-label"), Label("prayer-info-time-label"))
            for k in self.prayer_info_service.prayer_data.keys()
        }
        # # Initilize
        self.on_prayer_update(None, self.prayer_info_service.prayer_data)
        self.prayer_info_service.connect("update", self.on_prayer_update)

        for prayer in self.prayer_labels:
            self.add(
                CenterBox(
                    start_children=self.prayer_labels[prayer][0],
                    end_children=self.prayer_labels[prayer][1],
                )
            )

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
