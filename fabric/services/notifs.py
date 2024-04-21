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


class Notification(Service):
    def __init__(
        self,
        app_name,
        replaces_id,
        app_icon,
        summary,
        body,
        actions,
        hints,
        expire_timeout,
        connection,
        id,
        *args,
        **kwargs,
    ):
        self.app_name: str = app_name
        self.replaces_id: int = replaces_id
        self.app_icon: str = app_icon
        self.summary: str = summary
        self.body: str = body
        self.actions: list = actions
        self.hints: dict = hints
        self.expire_timeout: int = expire_timeout
        self._connection: Gio.DBusConnection = connection

        logger.info(f"New Notificaiton from application {self.app_name}")
        logger.info(f"App supports the following actions: {self.actions}")

        # GLib.idle_add(lambda: self.popup.toggle_popup())
        # self._connection.call_sync(
        #         FDN_BUS_NAME,
        #         FDN_BUS_PATH,
        #         FDN_BUS_NAME,
        #         "CloseNotification",
        #         GLib.Variant("(u)", [id]),
        #         None,
        #         Gio.DBusCallFlags.NONE,
        #         1000,
        #     )
        # This doesn't work unfortunatley :(
        GLib.timeout_add(
            1000,
            lambda: self._connection.emit_signal(
                FDN_BUS_NAME,
                FDN_BUS_PATH,
                FDN_BUS_NAME,
                "ActionInvoked",
                GLib.Variant("(us)", [id, "default"]),
            ),
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
            "Capabilities": GLib.Variant(
                "(as)",
                [
                    [
                        "action-icons",
                        "actions",
                        "body",
                        "body-hyperlinks",
                        "body-markup",
                        "icon-static",
                        "persistence",
                        "sound",
                    ]
                ],
            ),
        }

        match target:
            case "GetServerInformation":
                invocation.return_value(props["ServerInformation"])
            case "GetCapabilities":
                invocation.return_value(props["Capabilities"])
            case "Notify":
                self.curr_id += 1
                invocation.return_value(GLib.Variant("(u)", [self.curr_id]))
                new_notif = Notification(*params, self._connection, self.curr_id)

            case "CloseNotification":
                print("closed Notif", params[0])
                invocation.return_value(None)

            case _:
                print(target)
        return conn.flush()


nw = NotificationWatcher()
fabric.start()
