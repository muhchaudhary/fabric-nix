"""
Power profiles (power-saver / balanced / performance) from power-profiles-daemon.

`available` is False when the daemon isn't installed or running; the quick
settings row hides itself then.
"""

from fabric.core.service import Property, Service
from gi.repository import Gio, GLib
from loguru import logger

BUS_NAME = "org.freedesktop.UPower.PowerProfiles"
OBJECT_PATH = "/org/freedesktop/UPower/PowerProfiles"

PROFILES = ("power-saver", "balanced", "performance")


class PowerProfiles(Service):
    def __init__(self, **kwargs):
        self._proxy: Gio.DBusProxy | None = None
        super().__init__(**kwargs)
        Gio.DBusProxy.new_for_bus(
            Gio.BusType.SYSTEM,
            Gio.DBusProxyFlags.DO_NOT_AUTO_START,
            None,
            BUS_NAME,
            OBJECT_PATH,
            BUS_NAME,
            None,
            self._on_proxy,
        )

    def _on_proxy(self, _source, result: Gio.AsyncResult):
        try:
            self._proxy = Gio.DBusProxy.new_for_bus_finish(result)
        except GLib.Error as e:
            logger.info(f"[PowerProfiles] Unavailable: {e.message}")
            return
        self._proxy.connect("g-properties-changed", self._on_changed)
        self._proxy.connect("notify::g-name-owner", self._on_changed)
        self._on_changed()

    def _on_changed(self, *_):
        self.notify("available")
        self.notify("profile")

    @Property(bool, "readable", default_value=False)
    def available(self) -> bool:
        return self._proxy is not None and self._proxy.get_name_owner() is not None

    @Property(str, "read-write", default_value="balanced")
    def profile(self) -> str:
        if not self.available:
            return "balanced"
        value = self._proxy.get_cached_property("ActiveProfile")  # type: ignore[union-attr]
        return value.unpack() if value is not None else "balanced"

    @profile.setter
    def profile(self, value: str):
        if not self.available or value == self.profile:
            return

        def on_done(proxy: Gio.DBusProxy, result: Gio.AsyncResult):
            try:
                proxy.call_finish(result)
            except GLib.Error as e:
                logger.error(f"[PowerProfiles] Couldn't set {value}: {e.message}")

        self._proxy.call(  # type: ignore[union-attr]
            "org.freedesktop.DBus.Properties.Set",
            GLib.Variant(
                "(ssv)", (BUS_NAME, "ActiveProfile", GLib.Variant("s", value))
            ),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            on_done,
        )

    @property
    def profiles(self) -> list[str]:
        """The profiles this machine offers (performance needs hardware support)."""
        if not self.available:
            return []
        value = self._proxy.get_cached_property("Profiles")  # type: ignore[union-attr]
        offered = {p["Profile"] for p in value.unpack()} if value is not None else set()
        return [p for p in PROFILES if p in offered]
