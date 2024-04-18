from gi.repository import Gio, GLib
from loguru import logger

import fabric
from fabric.service import Service, Signal, SignalContainer
from fabric.utils import get_ixml, get_relative_path

# FDN: FreeDesktop Notifications

(FDN_BUS_NAME, FDN_BUS_IFACE_NODE, FDN_BUS_PATH) = (
    *get_ixml(
        get_relative_path("org.freedesktop.Notifications.xml"),
        "org.freedesktop.Notifications",
    ),
    "/org/freedesktop/Notifications",
)


class NotificationWatcher(Service):
    # __gsignals__ = SignalContainer(Signal("notification-recv", "run-first", None, ()))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.curr_id = 1
        self._notifications: dict[str, list] = {}
        self._connection: Gio.DBusConnection | None = None
        self.do_register()

    def do_register(self):
        return Gio.bus_own_name(
            Gio.BusType.SESSION,
            FDN_BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            self.on_bus_acquired,
            None,
            lambda *args: logger.warning(
                "[NotificationWatcher] can't own the DBus name, another notification service is probably running"
            ),
        )

    def on_bus_acquired(
        self, conn: Gio.DBusConnection, name: str, user_data: object = None
    ):
        self._connection = conn
        for interface in FDN_BUS_IFACE_NODE.interfaces:
            interface: Gio.DBusInterfaceInfo
            if interface.name == name:
                conn.register_object(FDN_BUS_PATH, interface, self.do_handle_bus_call)

    def do_handle_bus_call(
        self,
        conn: Gio.DBusConnection,
        sender: str,
        path: str,
        interface: str,
        target: str,
        params: GLib.Variant | tuple,
        invocation: Gio.DBusMethodInvocation,
        user_data: object = None,
    ):
        props = {
            "ServerInformation": GLib.Variant(
                "(ssss)", ("Fabric Notification Server", "example.org", "0.1", "1.2")
            ),
            "Capabilities": GLib.Variant("(as)", [["body", "actions", "action-icons"]]),
        }

        match target:
            case "GetServerInformation":
                invocation.return_value(props["ServerInformation"])
            case "GetCapabilities":
                invocation.return_value(props["Capabilities"])
            case "Notify":
                self.curr_id += 1
                print(params)
                invocation.return_value(GLib.Variant("(u)", [self.curr_id]))

            case _:
                print(target)
        return conn.flush()


nw = NotificationWatcher()
fabric.start()
