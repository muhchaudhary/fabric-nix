from typing import List

from gi.repository import GdkPixbuf, Gio, GLib
from loguru import logger

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

# TODO:
#   rewrite the whole thing
#   Implement propper notificication timeouts
#   Deal with multiple notification (store active notifs in an array or something)
#   Implement Signals and properties (sort of done)


class Notification(Service):
    __gsignals__ = SignalContainer(
        Signal("closed", "run-first", None, ()),
        Signal("invoked", "run-first", None, (str,)),
    )

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
        id,
        *args,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.app_name: str = app_name
        self.replaces_id: int = replaces_id
        self.app_icon: str = app_icon
        self.summary: str = summary
        self.body: str = body
        self.actions: list = actions
        self.id: int = id
        # There is a lot of info in the hints like pixbufs for app icons etc
        self.hints: dict = hints
        self.expire_timeout: int = expire_timeout

        logger.info(f"New Notificaiton from application: {self.app_name}")
        logger.info(f"Supports the following actions: {self.actions} \n")

    def close(self):
        self.emit("closed")

    def get_actions(self) -> List[str]:
        return self.actions

    def invoke(self, action_key: str):
        if action_key in self.actions:
            self.emit("invoked", action_key)

        # this shoudln't be done like this
        # I there can be notifications that take multiple actions
        self.emit("closed")

    # TODO: make images resizable, should be ez

    def get_image(self) -> GdkPixbuf.Pixbuf | None:
        # priority: image-data -> image-path -> icon_data
        if "image-data" in self.hints:
            image_data = self.hints.get("image-data")
            # image-data is of the format: (iiibiiay)
            #   0. width
            #   1. height
            #   2. rowstride
            #   3. has_alpha
            #   4. bits_per_sample (is always 8)
            #   5. channels
            #   6. image data in RBG byte order
            return GdkPixbuf.Pixbuf.new_from_bytes(
                data=GLib.Bytes.new(image_data[6]),
                colorspace=GdkPixbuf.Colorspace.RGB,
                has_alpha=image_data[3],
                bits_per_sample=image_data[4],
                width=image_data[0],
                height=image_data[1],
                rowstride=image_data[2],
            )

        if "image-path" in self.hints:
            image_path = self.hints.get("image-path")
            if "file://" in self.app_icon:
                # I haven't noticed this personally, but according to the spec,
                # the value should be a URI (file://...)
                return GdkPixbuf.Pixbuf.new_from_file(image_path[7:])
            return GdkPixbuf.Pixbuf.new_from_file(image_path)

        if "icon_data" in self.hints:
            image_data = self.hints.get("icon_data")
            return GdkPixbuf.Pixbuf.new_from_bytes(
                data=GLib.Bytes.new(image_data[6]),
                colorspace=GdkPixbuf.Colorspace.RGB,
                has_alpha=image_data[3],
                bits_per_sample=image_data[4],
                width=image_data.hints[0],
                height=image_data.hints[1],
                rowstride=image_data.hints[2],
            )

        return None

    def get_icon(self) -> GdkPixbuf.Pixbuf | None:
        if self.app_icon:
            if "file://" in self.app_icon:
                return GdkPixbuf.Pixbuf.new_from_file(self.app_icon[7:])

        # NOT IMPLEMENTED: app_icon can be a "name in a freedesktop.org-compliant icon theme"
        return None


class NotificationServer(Service):
    __gsignals__ = SignalContainer(
        Signal("notification-received", "run-first", None, (int,)),
        Signal("notification-closed", "run-first", None, (int,)),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.curr_id = 1
        self._notifications: dict[int, Notification] = {}
        self._connection: Gio.DBusConnection | None = None

        self.notification_server_props = {
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
        match target:
            case "GetServerInformation":
                invocation.return_value(
                    self.notification_server_props["ServerInformation"]
                )

            case "GetCapabilities":
                invocation.return_value(self.notification_server_props["Capabilities"])

            case "Notify":
                # Checking if replaces_id
                id, self.curr_id = (
                    (params[1], self.curr_id)
                    if params[1] != 0
                    else (self.curr_id, self.curr_id + 1)
                )
                invocation.return_value(GLib.Variant("(u)", [id]))
                self._notifications[id] = Notification(*params, id)
                self.add_notification(self._notifications[id])
                self.emit("notification-received", id)

            case "CloseNotification":
                id = params[0]
                self.emit("notification-closed", id)
                self._notifications[id].close() if id in self._notifications else None
                invocation.return_value(None)

            case _:
                print(target)
        return conn.flush()

    def get_notifications(self) -> List[Notification]:
        return self._notifications

    def get_notification_for_id(self, id: int) -> Notification | None:
        if id in self._notifications:
            return self._notifications[id]
        return None

    def add_notification(self, notification: Notification) -> None:
        def on_closed(notification):
            self._connection.emit_signal(
                None,
                FDN_BUS_PATH,
                FDN_BUS_NAME,
                "NotificationClosed",
                GLib.Variant("(uu)", [notification.id, 3]),
            )
            self._notifications.pop(notification.id)

        notification.connect("closed", on_closed)

        def on_invoke(notification, action_key):
            self._connection.emit_signal(
                None,
                FDN_BUS_PATH,
                FDN_BUS_NAME,
                "ActionInvoked",
                GLib.Variant("(us)", [notification.id, action_key]),
            )

        notification.connect("invoked", on_invoke)


# nw = NotificationServer()
# fabric.start()
