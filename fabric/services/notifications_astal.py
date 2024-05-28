import json
from typing import List, Literal

from gi.repository import GdkPixbuf
from loguru import logger

from fabric.service import Service, Signal, SignalContainer
from fabric.utils import invoke_repeater, exec_shell_command_async, exec_shell_command
from fabric.utils.fabricator import Fabricator

# FDN: FreeDesktop Notifications

DEFAULT_TIMEOUT = 10000


class Notification(Service):
    __gsignals__ = SignalContainer(
        Signal("closed", "run-first", None, ()),
        Signal("invoked", "run-first", None, (str,)),
    )

    def __init__(
        self,
        app_name,
        time,
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
        self.time: int = time
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
        self.start_timeout(
            expire_timeout
        ) if expire_timeout != -1 else self.start_timeout(DEFAULT_TIMEOUT)

    def start_timeout(self, timeout):
        invoke_repeater(timeout, lambda *args: [self.emit("closed"), False][1])

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
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_data)

        elif "image-path" in self.hints:
            image_path = self.hints.get("image-path")
            if image_path != "":
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)

        elif "icon_data" in self.hints:
            image_data = self.hints.get("icon_data")
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_data)
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
            if self.app_icon != "":
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.app_icon)

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


class NotificationServer(Service):
    __gsignals__ = SignalContainer(
        Signal("notification-received", "run-first", None, (object,)),
        Signal("notification-closed", "run-first", None, (int,)),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.notification_fab = Fabricator(poll_from="astal-notifd -d", stream=True)
        self.notification_fab.connect("changed", self.on_new_notification)

    def on_new_notification(self, _, notification):
        notification_dict = json.loads(notification)
        print(notification_dict)
        self.add_notification(
            Notification(
                id=notification_dict["id"],
                time=notification_dict["time"],
                expire_timeout=notification_dict["expire_timeout"],
                app_name=notification_dict["app_name"],
                app_icon=notification_dict["app_icon"],
                summary=notification_dict["summary"],
                body=notification_dict["body"],
                actions=notification_dict["actions"],
                hints=notification_dict["hints"],
            )
        )

    def get_notifications(self) -> List[Notification]:
        return exec_shell_command("astal-notifd -l")

    def add_notification(self, notification: Notification) -> None:
        def on_closed(notification):
            exec_shell_command_async(f"astal-notifd -c {notification.id}", None)
            self.emit("notification-closed", notification.id)

        notification.connect("closed", on_closed)

        def on_invoke(notification, action_key):
            exec_shell_command_async(
                f"astal-notifd -i {notification.id}:{action_key}", None
            )

        notification.connect("invoked", on_invoke)
        self.emit("notification-received", notification)

    # TODO GET ALL NOTIFS AT STARTUP
    def get_all_notficiatons(self):
        def on_get_response(*args):
            print(args)

        exec_shell_command_async("astal-notifd -l", on_get_response)
