import datetime
import json
import os

import requests
from gi.repository import GLib

from fabric.core.service import Property, Service, Signal
from fabric.utils import invoke_repeater

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label

from fabric_config.widgets.popup_window_v2 import PopupWindow

city = "Toronto"
country = "Canada"
api_request = (
    f"http://api.aladhan.com/v1/timingsByCity?city={city}&country={country}&method=2"
)

CACHE_DIR = GLib.get_user_cache_dir() + "/fabric"
PRAYER_TIMES_CACHE = CACHE_DIR + "/prayer-times"
PRAYER_TIMES_FILE = PRAYER_TIMES_CACHE + "/" + "current_times.json"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
if not os.path.exists(PRAYER_TIMES_CACHE):
    os.makedirs(PRAYER_TIMES_CACHE)
if not os.path.exists(PRAYER_TIMES_FILE):
    open(PRAYER_TIMES_FILE, "a").close()


class PrayerTimesService(Service):
    @Signal
    def update(self, json_data: object) -> object: ...

    @Signal
    def changed(self) -> None: ...

    def __init__(self, **kwargs):
        self.prayer_info: dict = {
            "Fajr": ["Fajr", ""],
            "Dhuhr": ["Dhuhr", ""],
            "Asr": ["Asr", ""],
            "Maghrib": ["Maghrib", ""],
            "Isha": ["Isha", ""],
        }
        super().__init__(**kwargs)
        invoke_repeater(
            12 * 60 * 60 * 60,
            lambda: self.get_data(False),
        )

    def refresh(self):
        self.get_data(True)
        return self.get_property("prayer-data")

    def get_data(self, run_once, *args):
        json_data = {}
        if os.stat(PRAYER_TIMES_FILE).st_size == 0:
            print("Getting Fresh Data")
            data = requests.get(api_request)
            with open(PRAYER_TIMES_FILE, "wb") as outfile:
                outfile.write(data.content)
                outfile.close()
        try:
            json_data = json.load(open(PRAYER_TIMES_FILE, "rb"))
        except Exception as _:
            return
        retrived_day = json_data["data"]["date"]["gregorian"]["date"]
        current_day = datetime.datetime.today().strftime("%d-%m-%Y")

        if retrived_day != current_day:
            try:
                data = requests.get(api_request)
                with open(PRAYER_TIMES_FILE, "wb") as outfile:
                    outfile.write(data.content)
                    outfile.close()
                json_data = json.load(open(PRAYER_TIMES_FILE, "rb"))
            except Exception as _:
                return False
        self.update_times(json_data)
        return True if not run_once else False

    @Property(object, "readable")
    def prayer_data(self) -> dict:
        return self.prayer_info

    def update_times(self, data):
        times = data["data"]["timings"]
        for prayer_name in self.prayer_info.keys():
            self.prayer_info[prayer_name][1] = times[prayer_name]
        self.notifier("prayer-data")
        self.update(self.prayer_info)

    def notifier(self, name: str, args=None):
        self.notify(name)
        self.changed()


class PrayerTimesButton(Button):
    def __init__(self, **kwargs):
        super().__init__(name="panel-button", **kwargs)
        self.prayer_button_label = Label(label="Prayer Times", name="panel-text")
        self.prayer_button_icon = Label(label="󰥹 ", name="panel-icon")
        self.add(Box(children=[self.prayer_button_icon, self.prayer_button_label]))
        self.connect("clicked", self.on_click)
        PrayerTimesPopup.reveal_child.revealer.connect(
            "notify::reveal-child",
            lambda *args: self.set_name("panel-button-active")
            if PrayerTimesPopup.popup_visible
            else self.set_name("panel-button"),
        )

    def on_click(self, button, *args):
        PrayerTimesPopup.toggle_popup()


class PrayerTimes(Box):
    def __init__(self, **kwargs):
        super().__init__(orientation="v", name="prayer-info", **kwargs)
        self.prayer_info_service = PrayerTimesService()
        self.fajr = Label()
        self.zhr = Label()
        self.asr = Label()
        self.mgrb = Label()
        self.isha = Label()

        self.fajr_time = Label()
        self.zhr_time = Label()
        self.asr_time = Label()
        self.mgrb_time = Label()
        self.isha_time = Label()

        # Initilize
        self.on_prayer_update(None, self.prayer_info_service.refresh())
        self.prayer_info_service.connect("update", self.on_prayer_update)

        self.add(CenterBox(start_children=self.fajr, end_children=self.fajr_time))
        self.add(CenterBox(start_children=self.zhr, end_children=self.zhr_time))
        self.add(CenterBox(start_children=self.asr, end_children=self.asr_time))
        self.add(CenterBox(start_children=self.mgrb, end_children=self.mgrb_time))
        self.add(CenterBox(start_children=self.isha, end_children=self.isha_time))

    def on_prayer_update(self, _, prayer_info):
        def time_format(time):
            d = datetime.datetime.strptime(time, "%H:%M")
            return d.strftime("  %I:%M %p")

        if prayer_info["Fajr"][1] == "":
            return
        self.fajr.set_label(prayer_info["Fajr"][0])
        self.fajr_time.set_label(time_format(prayer_info["Fajr"][1]))

        self.zhr.set_label(prayer_info["Dhuhr"][0])
        self.zhr_time.set_label(time_format(prayer_info["Dhuhr"][1]))

        self.asr.set_label(prayer_info["Asr"][0])
        self.asr_time.set_label(time_format(prayer_info["Asr"][1]))

        self.mgrb.set_label(prayer_info["Maghrib"][0])
        self.mgrb_time.set_label(time_format(prayer_info["Maghrib"][1]))

        self.isha.set_label(prayer_info["Isha"][0])
        self.isha_time.set_label(time_format(prayer_info["Isha"][1]))


PrayerTimesPopup = PopupWindow(
    transition_duration=350,
    anchor="top-left",
    transition_type="slide-down",
    child=PrayerTimes(),
    enable_inhibitor=True,
)
