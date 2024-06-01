from typing import List

import gi
from loguru import logger

from fabric.service import Service, Signal, SignalContainer

gi.require_version("AstalNotifd", "0.1")
from gi.repository import AstalNotifd


class NotificationServer(Service):
    __gsignals__ = SignalContainer(
        Signal("notification-received", "run-first", None, (object,)),
        Signal("notification-closed", "run-first", None, (int,)),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client: AstalNotifd.Notifd = AstalNotifd.Notifd.new()
        self._client.connect("active", self.on_client_ready)

    def on_client_ready(
        self, client: AstalNotifd.Notifd, active_type: AstalNotifd.ActiveType
    ):
        logger.info(
            f"Client is ready, in {'daemon' if active_type == AstalNotifd.ActiveType.DAEMON else 'proxy'} mode"
        )

        client.connect("notified", self.on_new_notification)
        client.connect(
            "resolved", lambda _, id, reason: self.emit("notification-closed", id)
        )

    def on_new_notification(self, client: AstalNotifd.Notifd, notification_id: int):
        logger.info(f"New notification with id: {notification_id}")
        new_notification: AstalNotifd.Notification = client.get_notification(
            notification_id
        )
        self.emit("notification-received", new_notification)

    def get_notifications(self) -> List[AstalNotifd.Notification]:
        return self._client.get_notifications()

    # TODO GET ALL NOTIFS AT STARTUP
    def get_all_notficiatons(self):
        pass


# ns = NotificationServer()
# fabric.start()
