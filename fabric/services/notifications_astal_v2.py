import gi
from loguru import logger

from fabric.core.service import Service

gi.require_version("AstalNotifd", "0.1")
from gi.repository import AstalNotifd


class NotificationServer(Service):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.astal_notifd: AstalNotifd.Notifd = AstalNotifd.Notifd.new()
        self.astal_notifd.connect("active", self.on_client_ready)

    def on_client_ready(
        self, client: AstalNotifd.Notifd, active_type: AstalNotifd.ActiveType
    ):
        logger.info(
            f"Client is ready, in {'daemon' if active_type == AstalNotifd.ActiveType.DAEMON else 'proxy'} mode"
        )

        client.connect("notified", self.on_new_notification)
        client.connect("resolved", self.on_notification_resolved)

    def on_new_notification(self, _, notification_id: int):
        logger.info(f"New notification with id: {notification_id}")

    def on_notification_resolved(
        self, _, notification_id: int, reason: AstalNotifd.ClosedReason
    ):
        logger.info(
            f"resolved notification with id: {notification_id} for reason {reason}"
        )
