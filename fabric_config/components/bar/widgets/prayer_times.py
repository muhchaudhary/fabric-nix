import datetime
import json
import os
import threading

import gi
from fabric.core.service import Property, Service, Signal
from fabric.utils import invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from gi.repository import Gio, GLib, Gtk
from loguru import logger

from fabric_config.components.bar.widgets.prayer_extras import (
    AdhanPlayer,
    QiblaCompass,
    compass_point,
    load_settings,
    notify,
    qibla_bearing,
    ramadan_countdown,
    save_settings,
)
from fabric_config.widgets.popup_window_v2 import PopupWindow
from fabric_config.widgets.toggle_pill import ToggleSwitch

gi.require_version("Geoclue", "2.0")
from gi.repository import Geoclue  # noqa: E402

CACHE_DIR = GLib.get_user_cache_dir() + "/fabric"
PRAYER_TIMES_CACHE = os.path.join(CACHE_DIR, "prayer-times")
PRAYER_TIMES_FILE = os.path.join(PRAYER_TIMES_CACHE, "current_times.json")
LOCATION_CACHE_FILE = os.path.join(PRAYER_TIMES_CACHE, "location.json")
os.makedirs(PRAYER_TIMES_CACHE, exist_ok=True)

# a heads-up this long before each prayer
REMIND_MINUTES = 10

# Geoclue can wait forever when it has no usable source (e.g. Wi-Fi off on a
# wired desktop) instead of failing, so give up and use the cached location
GEOCLUE_TIMEOUT_S = 10


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

    @Signal
    def prayer_soon(self, prayer: str, minutes: int) -> None:
        """The next prayer is REMIND_MINUTES away (once per prayer)."""

    @Signal
    def prayer_time(self, prayer: str) -> None:
        """A prayer's time has come (not fired for the one current at startup)."""

    def __init__(self, **kwargs):
        self.prayer_info: dict = {}
        self.settings = load_settings()
        self.adhan = AdhanPlayer()
        self._current_prayer = "None"
        self._next_prayer = "None"
        self._time_to_next_prayer = "None"
        self._location_name = ""
        self._announced: str | None = None
        self._reminded: str | None = None
        super().__init__(**kwargs)
        cached = _load_location()
        if cached:
            self._location_name = cached.get("city", "")
        # often enough to announce a prayer within seconds of its time
        invoke_repeater(15 * 1000, self.update_prayer_state)
        invoke_repeater(86400 * 1000, self._daily_refresh)

    def _daily_refresh(self) -> bool:
        # refresh() returns the prayer data, which is falsy until the first
        # fetch completes; return True so the repeating timer isn't cancelled
        self.refresh()
        return True

    @property
    def adhan_enabled(self) -> bool:
        return bool(self.settings.get("adhan", False))

    @adhan_enabled.setter
    def adhan_enabled(self, value: bool):
        self.settings["adhan"] = value
        save_settings(self.settings)
        if not value:
            self.adhan.stop()

    @property
    def hijri_month(self) -> int | None:
        data = self._read_json()
        try:
            return int(data["date"]["hijri"]["month"]["number"]) if data else None
        except (KeyError, TypeError, ValueError):
            return None

    def location(self) -> tuple[float, float] | None:
        cached = _load_location()
        if not cached:
            return None
        try:
            return float(cached["lat"]), float(cached["lon"])
        except (KeyError, TypeError, ValueError):
            return None

    def ramadan_countdown(self) -> str | None:
        return ramadan_countdown(
            self.prayer_info, self.hijri_month, datetime.datetime.now()
        )

    def _on_prayer_time(self, prayer: str):
        logger.info(f"[Prayer] {prayer} time")
        notify(f"{prayer}", f"It's time for {prayer}")
        if self.adhan_enabled:
            self.adhan.play(prayer)
        self.prayer_time(prayer)

    def update_prayer_state(self):
        # always return True: this runs on a repeating timer, and a falsy
        # return value would cancel it before the first fetch completes
        if not self.prayer_info:
            return True
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

        # a change after the first reading means a prayer's time just came
        # (the first reading is whatever was current at startup)
        current = str(self.current_prayer)
        if self._announced is not None and current != self._announced:
            self._on_prayer_time(current)
        self._announced = current

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

        seconds_left = time_to_next_prayer.total_seconds()
        upcoming = str(self.next_prayer)
        if 0 < seconds_left <= REMIND_MINUTES * 60 and self._reminded != upcoming:
            self._reminded = upcoming
            self.prayer_soon(upcoming, max(1, round(seconds_left / 60)))

        hours, remainder = divmod(int(time_to_next_prayer.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        self.time_to_next_prayer = f"{hours}h {minutes}m"

        return True

    @Property(object, "read-write")
    def current_prayer(self) -> str:
        return self._current_prayer

    @current_prayer.setter
    def current_prayer(self, value):
        self._current_prayer = value
        self.notify("current-prayer")

    @Property(object, "read-write")
    def next_prayer(self) -> str:
        return self._next_prayer

    @next_prayer.setter
    def next_prayer(self, value):
        self._next_prayer = value
        self.notify("next-prayer")

    @Property(object, "read-write")
    def time_to_next_prayer(self) -> str:
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
                if not cached:
                    self.location_name = ""
                    return
                self.location_name = cached.get("city", "")
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

        # cancelling after the request has finished is a no-op
        cancellable = Gio.Cancellable()
        GLib.timeout_add_seconds(GEOCLUE_TIMEOUT_S, cancellable.cancel)
        Geoclue.Simple.new(
            "fabric-config",
            Geoclue.AccuracyLevel.CITY,
            cancellable,
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
        self.prayer_button_label = Label(
            label="Prayer Times", name="panel-text", style_classes=["tnum"]
        )
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
        # in Ramadan, the countdown to Iftar or the end of Suhoor matters most
        if countdown := self.prayer_service.ramadan_countdown():
            self.prayer_button_label.set_label(countdown)
            return
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

        # rows are created as prayer data arrives; the data may still be
        # loading (fetched asynchronously) when this widget is built
        self.prayer_labels: dict[str, tuple[Label, Label]] = {}
        self.prayer_rows: dict[str, CenterBox] = {}
        self.add(Box(style_classes=["prayer-info-separator"]))
        self.on_prayer_update(None, self.prayer_info_service.prayer_data)
        self.prayer_info_service.connect("update", self.on_prayer_update)
        self.prayer_info_service.connect(
            "notify::current-prayer", self.update_prayer_label
        )
        self.update_prayer_label()
        self._add_extras()

    def _add_extras(self):
        service = self.prayer_info_service
        # rows go after the prayers; those arrive later, so keep them apart
        self.prayer_box = Box(orientation="v")
        for child in list(self.children)[2:]:
            self.remove(child)
            self.prayer_box.add(child)
        self.add(self.prayer_box)

        self.ramadan_label = Label("", name="prayer-info-ramadan")
        self.ramadan_label.set_no_show_all(True)

        self.compass = QiblaCompass()
        self.qibla_label = Label("", name="prayer-info-qibla", h_align="start")
        self.qibla_detail = Label("", name="prayer-info-detail", h_align="start")
        qibla = Box(
            name="prayer-info-extra",
            spacing=12,
            children=[
                self.compass,
                Box(
                    orientation="v",
                    v_align="center",
                    children=[self.qibla_label, self.qibla_detail],
                ),
            ],
        )

        self.adhan_switch = ToggleSwitch(
            active=service.adhan_enabled,
            on_toggled=lambda active: setattr(service, "adhan_enabled", active),
        )
        self.adhan_switch.set_valign(Gtk.Align.CENTER)
        self.stop_button = Button(
            label="Stop",
            name="prayer-info-stop",
            on_clicked=lambda *_: self._stop_adhan(),
        )
        self.stop_button.set_no_show_all(True)
        adhan = CenterBox(
            name="prayer-info-extra",
            start_children=Box(
                orientation="v",
                v_align="center",
                children=[
                    Label("Adhan", name="prayer-info-qibla", h_align="start"),
                    Label(
                        "At each prayer's time",
                        name="prayer-info-detail",
                        h_align="start",
                    ),
                ],
            ),
            end_children=Box(spacing=8, children=[self.stop_button, self.adhan_switch]),
        )

        self.add(self.ramadan_label)
        self.add(Box(style_classes=["prayer-info-separator"]))
        self.add(qibla)
        self.add(adhan)

        service.connect("prayer-time", lambda *_: self.stop_button.show())
        service.connect("notify::location-name", lambda *_: self.update_extras())
        service.connect("notify::time-to-next-prayer", lambda *_: self.update_extras())
        self.update_extras()

    def _stop_adhan(self):
        self.prayer_info_service.adhan.stop()
        self.stop_button.hide()

    def update_extras(self):
        service = self.prayer_info_service
        location = service.location()
        if location is None:
            self.compass.set_bearing(None)
            self.qibla_label.set_label("Qibla")
            self.qibla_detail.set_label("Location unknown")
        else:
            bearing = qibla_bearing(*location)
            self.compass.set_bearing(bearing)
            self.qibla_label.set_label(
                f"Qibla {round(bearing)}° {compass_point(bearing)}"
            )
            self.qibla_detail.set_label("Clockwise from true north")

        countdown = service.ramadan_countdown()
        self.ramadan_label.set_visible(countdown is not None)
        self.ramadan_label.set_label(
            f"Ramadan Mubarak · {countdown}" if countdown else ""
        )
        if not service.adhan.playing:
            self.stop_button.hide()

    def update_location_label(self, *_):
        name = self.prayer_info_service.location_name
        self.location_label.set_label(name or "Unknown location")

    def on_refresh(self, *_):
        self.location_label.set_label("Fetching location...")
        self.prayer_info_service.force_refresh()

    def update_prayer_label(self, *_):
        current = self.prayer_info_service.current_prayer
        for name, row in self.prayer_rows.items():
            row.style_classes = (
                ["prayer-info-row", "urgent"]
                if name == current
                else ["prayer-info-row"]
            )

    def _add_prayer_row(self, prayer: str):
        parent = getattr(self, "prayer_box", self)
        if self.prayer_rows:
            parent.add(Box(style_classes=["prayer-info-separator"]))
        labels = (
            Label(style_classes=["prayer-info-prayer-label"]),
            Label(style_classes=["prayer-info-time-label"]),
        )
        row = CenterBox(
            style_classes=["prayer-info-row"],
            start_children=labels[0],
            end_children=labels[1],
        )
        self.prayer_labels[prayer] = labels
        self.prayer_rows[prayer] = row
        parent.add(row)

    def on_prayer_update(self, _, prayer_info):
        def time_format(time):
            d = datetime.datetime.strptime(time, "%H:%M")
            return d.strftime("%I:%M %p")

        for info in prayer_info:
            if info not in self.prayer_labels:
                self._add_prayer_row(info)
            self.prayer_labels[info][0].set_label(info)
            self.prayer_labels[info][1].set_label(time_format(prayer_info[info]))


PrayerTimesPopup = PopupWindow(
    transition_duration=350,
    anchor="top-left",
    transition_type="slide-down",
    child=PrayerTimes(),
    enable_inhibitor=True,
)
