import datetime
import json
import os
import threading

import gi
from fabric.core.service import Property, Service, Signal
from fabric.utils import exec_shell_command_async, invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from gi.repository import GLib

gi.require_version("Geoclue", "2.0")
from gi.repository import Geoclue

from fabric_config.widgets.popup_window_v2 import PopupWindow

CACHE_DIR = GLib.get_user_cache_dir() + "/fabric"
PRAYER_TIMES_CACHE = os.path.join(CACHE_DIR, "prayer-times")
PRAYER_TIMES_FILE = os.path.join(PRAYER_TIMES_CACHE, "current_times.json")
LOCATION_CACHE_FILE = os.path.join(PRAYER_TIMES_CACHE, "location.json")
os.makedirs(PRAYER_TIMES_CACHE, exist_ok=True)


def _save_location(lat: float, lon: float, city: str = ""):
    try:
        with open(LOCATION_CACHE_FILE, "w") as f:
            json.dump({"lat": lat, "lon": lon, "city": city}, f)
    except Exception:
        pass


def _load_location() -> dict | None:
    try:
        with open(LOCATION_CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def _reverse_geocode(lat: float, lon: float) -> str:
    try:
        import requests

        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        resp = requests.get(url, timeout=5, headers={"User-Agent": "fabric-config/1.0"})
        if resp.status_code == 200:
            addr = resp.json().get("address", {})
            city = (
                addr.get("city")
                or addr.get("town")
                or addr.get("village")
                or addr.get("county", "")
            )
            country = addr.get("country", "")
            return ", ".join(x for x in [city, country] if x)
    except Exception:
        pass
    return f"{lat:.2f}°, {lon:.2f}°"


class PrayerTimesService(Service):
    @Signal
    def update(self, _json_data: object) -> object: ...

    @Signal
    def changed(self) -> None: ...

    def __init__(self, **kwargs):
        self.prayer_info: dict = {}
        self._current_prayer = "None"
        self._next_prayer = "None"
        self._time_to_next_prayer = "None"
        self._location_name = ""
        super().__init__(**kwargs)
        cached = _load_location()
        if cached:
            self._location_name = cached.get("city", "")
        invoke_repeater(1000 * 60, self.update_prayer_state)
        invoke_repeater(86400 * 1000, lambda: self.refresh())

    def notify_next_prayer(self):
        exec_shell_command_async(
            f"notify-send 'Next Prayer' 'Next prayer is {self.next_prayer}'",
            lambda *_: None,
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

    @Property(str, "read-write")
    def location_name(self) -> str:
        return self._location_name

    @location_name.setter
    def location_name(self, value: str):
        self._location_name = value
        self.notify("location-name")

    def refresh(self):
        self._request_data() if self._refresh_needed() else self.update_times(
            self._read_json()
        )
        return self.get_property("prayer-data")

    def force_refresh(self):
        self._request_data()

    def _fetch_with_coords(self, lat: float, lon: float):
        import requests

        ts = int(datetime.datetime.now().timestamp())
        url = f"http://api.aladhan.com/v1/timings/{ts}?latitude={lat}&longitude={lon}&method=2"
        try:
            response = requests.get(url=url, timeout=10)
            if response.status_code == 200:
                with open(PRAYER_TIMES_FILE, "w") as outfile:
                    json.dump(response.json()["data"], outfile, indent=4)
                data = self._read_json()
                GLib.idle_add(lambda: self.update_times(data))
        except Exception:
            pass

    def _request_data(self):
        def on_geoclue_ready(_, result):
            try:
                simple = Geoclue.Simple.new_finish(result)
                loc = simple.get_location()
                lat = loc.get_property("latitude")
                lon = loc.get_property("longitude")
            except Exception:
                cached = _load_location()
                if cached:
                    GLib.idle_add(
                        lambda: setattr(self, "location_name", cached.get("city", ""))
                    )
                    threading.Thread(
                        target=self._fetch_with_coords,
                        args=(cached["lat"], cached["lon"]),
                        daemon=True,
                    ).start()
                return

            def fetch():
                city = _reverse_geocode(lat, lon)
                _save_location(lat, lon, city)
                GLib.idle_add(lambda: setattr(self, "location_name", city))
                self._fetch_with_coords(lat, lon)

            threading.Thread(target=fetch, daemon=True).start()

        Geoclue.Simple.new(
            "fabric-config",
            Geoclue.AccuracyLevel.CITY,
            None,
            on_geoclue_ready,
        )

    def _read_json(self) -> dict | None:
        try:
            with open(PRAYER_TIMES_FILE) as infile:
                return json.load(infile)
        except Exception:
            return None

    def _refresh_needed(self) -> bool:
        data = self._read_json()
        if data:
            retrieved_day = data["date"]["gregorian"]["date"]
            current_day = datetime.datetime.today().strftime("%d-%m-%Y")
            return retrieved_day != current_day
        return True

    @Property(object, "readable")
    def prayer_data(self) -> dict:
        return self.prayer_info

    def update_times(self, data):
        times = data["timings"]
        for prayer_name in ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]:
            self.prayer_info[prayer_name] = times[prayer_name]
        self.notifier("prayer-data")
        self.emit("update", self.prayer_info)
        self.update_prayer_state()

    def notifier(self, name: str, _args=None):
        self.notify(name)
        self.emit("changed")


_prayer_service: "PrayerTimesService | None" = None


def _get_prayer_service() -> "PrayerTimesService":
    global _prayer_service
    if _prayer_service is None:
        _prayer_service = PrayerTimesService()
    return _prayer_service


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
        self.prayer_service = _get_prayer_service()
        self.prayer_service.connect("notify::current-prayer", self.update_label)
        self.prayer_service.connect("notify::time-to-next-prayer", self.update_label)
        self.update_label()
        PrayerTimesPopup.reveal_child.revealer.connect(
            "notify::reveal-child",
            lambda *_: (
                [
                    self.add_style_class("button-basic-active"),
                    self.remove_style_class("button-basic"),
                ]
                if PrayerTimesPopup.popup_visible
                else [
                    self.remove_style_class("button-basic-active"),
                    self.add_style_class("button-basic"),
                ]
            ),
        )

    def on_click(self, *_):
        PrayerTimesPopup.toggle_popup()

    def update_label(self, *_):
        self.prayer_button_label.set_label(
            f"{self.prayer_service.current_prayer} ({self.prayer_service.time_to_next_prayer} left)"
        )


class PrayerTimes(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="v", name="prayer-info", style_classes=["cool-border"], **kwargs
        )
        self.prayer_info_service = _get_prayer_service()

        self.location_label = Label(
            label=self.prayer_info_service.location_name or "Fetching location...",
            name="prayer-info-location",
        )
        self.refresh_button = Button(
            label="󰑐",
            name="prayer-info-refresh",
            tooltip_text="Refresh location and prayer times",
            on_clicked=self.on_refresh,
        )
        self.add(
            CenterBox(
                name="prayer-info-header",
                start_children=Label(label=" ", name="prayer-info-location-icon"),
                center_children=self.location_label,
                end_children=self.refresh_button,
            )
        )
        self.prayer_info_service.connect(
            "notify::location-name", self.update_location_label
        )

        self.prayer_labels = {
            k: (
                Label(style_classes=["prayer-info-prayer-label"]),
                Label(style_classes=["prayer-info-time-label"]),
            )
            for k in self.prayer_info_service.prayer_data.keys()
        }
        self.on_prayer_update(None, self.prayer_info_service.prayer_data)
        self.prayer_info_service.connect("update", self.on_prayer_update)
        self.add(Box(style_classes=["prayer-info-separator"]))
        for i, prayer in enumerate(self.prayer_labels):
            if i > 0:
                self.add(Box(style_classes=["prayer-info-separator"]))
            self.add(
                CenterBox(
                    style_classes=["prayer-info-row"],
                    start_children=self.prayer_labels[prayer][0],
                    end_children=self.prayer_labels[prayer][1],
                )
            )
        self.prayer_info_service.connect(
            "notify::current-prayer", self.update_prayer_label
        )
        self.update_prayer_label()

    def update_location_label(self, *_):
        name = self.prayer_info_service.location_name
        self.location_label.set_label(name or "Unknown location")

    def on_refresh(self, *_):
        self.location_label.set_label("Fetching location...")
        self.prayer_info_service.force_refresh()

    def update_prayer_label(self, *_):
        for label in self.prayer_labels.values():
            label[0].get_parent().get_parent().get_parent().style_classes = [
                "prayer-info-row"
            ]
        if self.prayer_info_service.current_prayer in self.prayer_labels:
            self.prayer_labels[self.prayer_info_service.current_prayer][
                0
            ].get_parent().get_parent().get_parent().style_classes = [
                "prayer-info-row",
                "urgent",
            ]

    def on_prayer_update(self, _, prayer_info):
        def time_format(time):
            d = datetime.datetime.strptime(time, "%H:%M")
            return d.strftime("%I:%M %p")

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
