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

from widgets.popup_window import PopupWindow

city = "Ottawa"
country = "Canada"
api_request = (
    f"http://api.aladhan.com/v1/timingsByCity?city={city}&country={country}&method=2"
)

# General setup and env vars
CACHE_DIR = GLib.get_user_cache_dir() + "/fabric"
PRAYER_TIMES_CACHE = CACHE_DIR + "/prayer_times"
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
        self.names = ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]
        self.curr_fajr_time = ""
        self.curr_zuhr_time = ""
        self.curr_asr_time = ""
        self.curr_maghrib_time = ""
        self.curr_isha_time = ""

        self.failed_attempts = 0
        self.max_tries = 10

        super().__init__(**kwargs)
        invoke_repeater(
            12 * 60 * 60 * 60,
            lambda: self._parse_json(),
        )
        self._parse_json()

    # Properties
    def time_format(self, time) -> str:
        try:
            d = datetime.datetime.strptime(time, "%H:%M")
        except ValueError:
            return time
        else:
            return d.strftime("  %I:%M %p")

    @Property(value_type=str, flags="readable")
    def fajr_time(self) -> str:
        return self.time_format(self.curr_fajr_time)

    @Property(value_type=str, flags="readable")
    def zuhr_time(self) -> str:
        return self.time_format(self.curr_zuhr_time)

    @Property(value_type=str, flags="readable")
    def asr_time(self) -> str:
        return self.time_format(self.curr_asr_time)

    @Property(value_type=str, flags="readable")
    def maghrib_time(self) -> str:
        return self.time_format(self.curr_maghrib_time)

    @Property(value_type=str, flags="readable")
    def isha_time(self) -> str:
        return self.time_format(self.curr_isha_time)

    def _do_request(self) -> None:
        logger.info("[PrayerTimes] Requesting data from server")
        try:
            data = requests.get(api_request)
        except:
            logger.error("[PrayerTimes] Failed to get data")
        else:
            with open(PRAYER_TIMES_FILE, "wb") as outfile:
                outfile.write(data.content)
                outfile.close()
        try:
            json_data = json.load(open(PRAYER_TIMES_FILE, "rb"))
        except Exception as e:
            return
        retrived_day = json_data["data"]["date"]["gregorian"]["date"]
        current_day = datetime.datetime.today().strftime("%d-%m-%Y")

        if retrived_day != current_day:
            print("Getting Fresh Data")
            data = requests.get(api_request)
            with open(PRAYER_TIMES_FILE, "wb") as outfile:
                outfile.write(data.content)
                outfile.close()
            json_data = json.load(open(PRAYER_TIMES_FILE, "rb"))
        except ValueError:
            logger.info(
                "[PrayerTimes] Could not read from local storage, atttempting to grab: "
                + f"{self.failed_attempts}"
            )
            if self.failed_attempts == self.max_tries:
                logger.info("[PrayerTimes] Maximum fetch attempts exceeded, giving up")
                return None
            self.failed_attempts += 1
            self._do_request()
            self._parse_json()
        else:
            logger.info("[PrayerTimes] Data is cached, proceeding")
            retrived_day: str = json_data["data"]["date"]["gregorian"]["date"]
            current_day: str = GLib.DateTime.new_now_local().format("%d-%m-%Y")
            if retrived_day != current_day:
                # TODO: move to tmp file instead and move back if we couldn't grab latest data
                os.rename(PRAYER_TIMES_FILE, PRAYER_TIMES_FILE + ".old")
                self._parse_json()
                return
            times = json_data["data"]["timings"]
            self.curr_fajr_time = times[self.names[0]]
            self.curr_zuhr_time = times[self.names[1]]
            self.curr_asr_time = times[self.names[2]]
            self.curr_maghrib_time = times[self.names[3]]
            self.curr_isha_time = times[self.names[4]]
            self.notify_all()

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


class PrayerTimesWidget(Box):
    def __init__(self, **kwargs):
        super().__init__(orientation="v", name="prayer-info", **kwargs)
        self.service: PrayerTimes = PrayerTimes()
        self.fajr = Label("Fajr")
        self.zhr = Label("Zuhr")
        self.asr = Label("Asr")
        self.mgrb = Label("Maghrib")
        self.isha = Label("Isha")

        self.fajr_time = Label()
        self.zhr_time = Label()
        self.asr_time = Label()
        self.mgrb_time = Label()
        self.isha_time = Label()

        self.service.bind_property("fajr-time", self.fajr_time, "label")
        self.service.bind_property("zuhr-time", self.zhr_time, "label")
        self.service.bind_property("asr-time", self.asr_time, "label")
        self.service.bind_property("maghrib-time", self.mgrb_time, "label")
        self.service.bind_property("isha-time", self.isha_time, "label")

        self.service.notify_all()

        # Initilize

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


class PrayerTimesButton(Button):
    def __init__(self, **kwargs):
        super().__init__(name="panel-button", **kwargs)
        self.prayer_button_label = Label(label="Prayer Times", name="panel-text")
        self.prayer_button_icon = Label(label="󰥹 ", name="panel-icon")
        self.add(Box(children=[self.prayer_button_icon, self.prayer_button_label]))
        self.connect("clicked", self.on_click)
        PrayerTimesPopup.revealer.connect(
            "notify::reveal-child",
            lambda *args: self.set_name("panel-button-active")
            if PrayerTimesPopup.visible
            else self.set_name("panel-button"),
        )

    def on_click(self, button, *args):
        PrayerTimesPopup.toggle_popup_offset(
            button.get_allocation().x,
            button.get_allocated_width(),
        )


PrayerTimesPopup = PopupWindow(
    transition_duration=350,
    anchor="top left",
    transition_type="slide-down",
    child=PrayerTimesWidget(),
    enable_inhibitor=True,
)
