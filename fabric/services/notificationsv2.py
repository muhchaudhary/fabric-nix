from typing import List, Literal
import gi

from mydbus import DBusClient
from fabric.utils import get_ixml, get_relative_path
import fabric
from fabric.service import Service, Signal, SignalContainer
from loguru import logger
from fabric.utils import invoke_repeater

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GLib, GdkPixbuf  # noqa: E402


(FDN_BUS_NAME, FDN_BUS_IFACE_NODE, FDN_BUS_PATH) = (
    *get_ixml(
        get_relative_path("org.freedesktop.Notifications.xml"),
        "org.freedesktop.Notifications",
    ),
    "/org/freedesktop/Notifications",
)

DEFAULT_TIMEOUT = 10000


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
        notification_server,
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
        # There is a lot of info in the hints like pixbufs for app icons etc
        self.hints: dict = hints
        self.id: int = id
        self.notification_server: NoitificationClient = notification_server
        self.expire_timeout: int = expire_timeout

        logger.info(f"New Notificaiton from application: {self.app_name}")
        logger.info(f"Supports the following actions: {self.actions} \n")

        self.start_timeout(
            expire_timeout
        ) if expire_timeout != -1 else self.start_timeout(DEFAULT_TIMEOUT)

    def start_timeout(self, timeout):
        invoke_repeater(timeout, lambda *args: [self.close(1), False][1])

    def close(
        self,
        reason: Literal[
            "expired",
            "dismissed",
            "closed",
            "undefined",
        ] = "closed",
    ):
        self.emit("closed")
        self.notification_server.emit_bus_signal(
            "NotificationClosed",
            GLib.Variant(
                "(uu)",
                [
                    self.id,
                    {
                        "expired": 1,
                        "dismissed": 2,
                        "closed": 3,
                        "undefined": 4,
                    }.get(reason, 3),
                ],
            ),
        )

    def get_actions(self) -> List[str]:
        return self.actions

    def invoke(self, action_key: str):
        if action_key in self.actions:
            self.emit("invoked")
            self.notification_server.emit_bus_signal(
                "ActionInvoked",
                GLib.Variant("(us)", [self.id, action_key]),
            )

        # Should not be done like this btw
        # I there can be notifications that take multiple actions
        self.close()

    def get_image_pixbuf(
        self,
        width=128,
        height=128,
        resize_method: Literal[
            "hyper",
            "bilinear",
            "nearest",
            "tiles",
        ] = "nearest",
    ) -> GdkPixbuf.Pixbuf | None:
        # priority: image-data -> image-path -> icon_data
        pixbuf = None
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
            pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
                data=GLib.Bytes.new(image_data[6]),
                colorspace=GdkPixbuf.Colorspace.RGB,
                has_alpha=image_data[3],
                bits_per_sample=image_data[4],
                width=image_data[0],
                height=image_data[1],
                rowstride=image_data[2],
            )

        elif "image-path" in self.hints:
            image_path = self.hints.get("image-path")
            if "file://" in image_path:
                # I haven't noticed this personally, but according to the spec,
                # the value should be a URI (file://...)
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path[7:])
            else:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)

        elif "icon_data" in self.hints:
            image_data = self.hints.get("icon_data")
            pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
                data=GLib.Bytes.new(image_data[6]),
                colorspace=GdkPixbuf.Colorspace.RGB,
                has_alpha=image_data[3],
                bits_per_sample=image_data[4],
                width=image_data.hints[0],
                height=image_data.hints[1],
                rowstride=image_data.hints[2],
            )
        return (
            pixbuf.scale_simple(
                width,
                height,
                {
                    "hyper": GdkPixbuf.InterpType.HYPER,
                    "bilinear": GdkPixbuf.InterpType.BILINEAR,
                    "nearest": GdkPixbuf.InterpType.NEAREST,
                    "tiles": GdkPixbuf.InterpType.TILES,
                }.get(resize_method.lower(), GdkPixbuf.InterpType.NEAREST),
            )
            if pixbuf is not None
            else pixbuf
        )

    def get_icon_pixbuf(
        self,
        width=128,
        height=128,
        resize_method: Literal[
            "hyper",
            "bilinear",
            "nearest",
            "tiles",
        ] = "nearest",
    ) -> GdkPixbuf.Pixbuf | None:
        pixbuf = None
        if self.app_icon:
            if "file://" in self.app_icon:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.app_icon[7:])

        # NOT IMPLEMENTED: app_icon can be a "name in a freedesktop.org-compliant icon theme"
        return (
            pixbuf.scale_simple(
                width,
                height,
                {
                    "hyper": GdkPixbuf.InterpType.HYPER,
                    "bilinear": GdkPixbuf.InterpType.BILINEAR,
                    "nearest": GdkPixbuf.InterpType.NEAREST,
                    "tiles": GdkPixbuf.InterpType.TILES,
                }.get(resize_method.lower(), GdkPixbuf.InterpType.NEAREST),
            )
            if pixbuf is not None
            else pixbuf
        )


class NoitificationClient(DBusClient):
    __gsignals__ = SignalContainer(
        Signal("notification-received", "run-first", None, (int,)),
        Signal("notification-closed", "run-first", None, (int,)),
    )

    def __init__(self, **kwargs) -> None:
        super().__init__(FDN_BUS_NAME, FDN_BUS_PATH, FDN_BUS_IFACE_NODE, **kwargs)
        self.connect("name-own-error", lambda *args: self.on_name_own_error())
        self.connect("name-owned", lambda *args: self.on_name_owned())
        self.current_id = 1
        self._notifications: dict[int, Notification] = {}
        self.caps = GLib.Variant(
            "(as)",
            [
                [
                    # "action-icons",
                    "actions",
                    "body",
                    "body-hyperlinks",
                    "body-markup",
                    # "icon-static",
                    # "persistence",
                    # "sound",
                ]
            ],
        )

    def on_name_owned_error(self):
        logger.error("[Notification] Failed to Start Notification Client")

    def on_name_owned(self):
        logger.info("[Notification] Notification Client Started")
        # Returns notification ID and reason
        # 1 - The notification expired.
        # 2 - The notification was dismissed by the user.
        # 3 - The notification was closed by a call to CloseNotification.
        # 4 - Undefined/reserved reasons.
        self.connect_bus_signal(
            "NotificationClosed",
            lambda conn,
            destination_bus_name,
            object_path,
            interface_name,
            signal_name,
            data,
            _: self.close_notification(data[0]),
        )

        self.connect_bus_signal(
            "ActionInvoked",
            lambda conn,
            destination_bus_name,
            object_path,
            interface_name,
            signal_name,
            data,
            _: self.invoke_action(*data),
        )

    def get_notification_for_id(self, id) -> Notification | None:
        return self._notifications.get(id, None)

    @DBusClient.method_handler()
    def get_server_information(self, *args):
        return GLib.Variant(
            "(ssss)", ("Fabric Notification Serivce", "fabric.org", "0.1", "1.2")
        )

    @DBusClient.method_handler()
    def get_capabilities(self, *args):
        return self.caps

    @DBusClient.method_handler()
    def notify(self, _, *params):
        nf_return: GLib.Variant = params[0]
        # I hate you spotify
        if nf_return[0] == "Spotify":
            return GLib.Variant("(u)", [0])

        id, self.current_id = (
            (nf_return[1], self.current_id)
            if nf_return[1] != 0
            else (self.current_id, self.current_id + 1)
        )
        self._notifications[id] = Notification(*nf_return, id, self)
        self.emit("notification-received", id)
        return GLib.Variant("(u)", [id])

    @DBusClient.method_handler()
    def close_notification(self, closed_id):
        logger.info(f"[Notification] Closed Notification With id {closed_id}")
        self.emit("notification-closed", closed_id)
        if closed_id in self._notifications:
            del self._notifications[closed_id]
        return None

    @DBusClient.method_handler()
    def invoke_action(self, id, action_id):
        logger.info(
            f"[Notification] Invoking action {action_id} of notification with id {id}"
        )
        self._notifications[id].invoke(
            action_id
        ) if id in self._notifications else logger.error(
            "[Notifications] Tried to invoke action of notificaiton that doesn't exist"
        )
        return None


nc = NoitificationClient()


fabric.start()
