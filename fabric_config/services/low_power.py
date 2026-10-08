"""
Low-power mode: on while the power-saver profile is active or the machine
runs on battery.

While it's on, the bar does less in the background: the desktop's drawn
layer (weather, visualizer) stops animating and shows a still frame, cava
isn't run for the desktop, and system stats are sampled less often (unless
the stats popup is open). Things you interact with keep working as usual.
"""

from fabric.core.service import Property, Service
from gi.repository import Gio, GLib
from loguru import logger

from fabric_config.services.power_profiles import PowerProfiles

UPOWER = "org.freedesktop.UPower"
UPOWER_PATH = "/org/freedesktop/UPower"


class LowPower(Service):
    def __init__(self, power_profiles: PowerProfiles, **kwargs):
        super().__init__(**kwargs)
        self._profiles = power_profiles
        self._upower: Gio.DBusProxy | None = None
        self._active = False
        power_profiles.connect("notify::profile", lambda *_: self._update())
        Gio.DBusProxy.new_for_bus(
            Gio.BusType.SYSTEM,
            Gio.DBusProxyFlags.DO_NOT_AUTO_START,
            None,
            UPOWER,
            UPOWER_PATH,
            UPOWER,
            None,
            self._on_proxy,
        )
        self._update()

    def _on_proxy(self, _source, result: Gio.AsyncResult):
        try:
            self._upower = Gio.DBusProxy.new_for_bus_finish(result)
        except GLib.Error as e:
            logger.info(f"[LowPower] UPower unavailable: {e.message}")
            return
        self._upower.connect("g-properties-changed", lambda *_: self._update())
        self._update()

    @property
    def on_battery(self) -> bool:
        if self._upower is None:
            return False
        value = self._upower.get_cached_property("OnBattery")
        return bool(value.unpack()) if value is not None else False

    @Property(bool, "readable", default_value=False)
    def active(self) -> bool:
        return self._active

    def _update(self):
        active = self._profiles.profile == "power-saver" or self.on_battery
        if active != self._active:
            self._active = active
            logger.info(f"[LowPower] {'on' if active else 'off'}")
            self.notify("active")
