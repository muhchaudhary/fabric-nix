import gi
from loguru import logger

from fabric.core.service import Service

gi.require_version("AstalNotifd", "0.1")
from gi.repository import AstalNotifd


class NotificationServer(Service):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.astal_notifd: AstalNotifd.Notifd = AstalNotifd.Notifd.get_default()
        self.astal_notifd.connect("notified", self.on_new_notification)
        self.astal_notifd.connect("resolved", self.on_notification_resolved)

    def on_new_notification(self, _, id: int, is_replaced: bool):
        logger.info(f"New notification with id: {id}")

    def on_notification_resolved(
        self, _, notification_id: int, reason: AstalNotifd.ClosedReason
    ):
        logger.info(
            f"resolved notification with id: {notification_id} for reason {reason}"
        )
