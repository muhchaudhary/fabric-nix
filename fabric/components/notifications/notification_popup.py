import gi
from services.notifications_astal_v2 import NotificationServer

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow
from fabric.widgets.centerbox import CenterBox

from fabric.utils import invoke_repeater
from loguru import logger

gi.require_version("AstalNotifd", "0.1")
from gi.repository import AstalNotifd  # noqa: E402

# TODO: make a notification center
# TODO: group notifications by type


class NotificationBox(Box):
    def __init__(self, notification: AstalNotifd.Notification):
        self.app_body = notification.get_body()
        self.app_title = notification.get_summary()

        self.action_buttons = [
            Button(
                label=action.label,
                on_clicked=lambda *_: notification.invoke(action.id),
                h_expand=True,
            )
            for action in notification.get_actions()
        ]

        logger.error(f"APP ICON: {notification.get_app_icon()}")

        self.notification_box = CenterBox(
            name="notification-box",
            orientation="v",
            start_children=[
                Box(
                    spacing=5,
                    children=[
                        Image(
                            icon_name=notification.get_app_icon()
                            if notification.get_app_icon()
                            else "dialog-information-symbolic"
                        ),
                        Label(
                            markup=f"<span font_weight='heavy' >{
                                        notification.get_app_name()
                                        }</span>",
                            h_align="start",
                        ),
                    ],
                )
            ],
            center_children=[
                Box(
                    name="notification-content",
                    spacing=10,
                    children=[
                        Box(
                            name="notification-image",
                            style=f"background-image: url('{notification.get_image() }')",
                        ),
                        Box(
                            orientation="v",
                            children=[
                                Label(
                                    markup=f"<span font_weight='heavy' >{
                                        notification.get_summary()
                                        }</span>  \n"
                                    + notification.get_body(),
                                    line_wrap="char",
                                    max_chars_width=40,
                                    h_align="start",
                                ),
                            ],
                        ),
                    ],
                )
            ],
            end_children=[
                Box(
                    name="notification-action-buttons",
                    children=self.action_buttons,
                    h_expand=True,
                )
            ],
        )

        super().__init__(children=self.notification_box)


class NotificationRevealer(Revealer):
    def __init__(self, notification: AstalNotifd.Notification, **kwargs):
        self.popup_timeout = 5000
        super().__init__(
            child=NotificationBox(notification),
            transition_duration=500,
            transition_type="slide-right",
        )
        invoke_repeater(self.popup_timeout, lambda *_: self.set_reveal_child(False))
        self.connect(
            "notify::child-revealed",
            lambda *args: self.destroy() if not self.get_child_revealed() else None,
        )

    def on_resolved(self, _, closed_reason: AstalNotifd.ClosedReason):
        reason = ""
        match closed_reason:
            case AstalNotifd.ClosedReason.EXPIRED:
                reason = "expired"
            case AstalNotifd.ClosedReason.DISMISSED_BY_USER:
                reason = "closed by user"
            case AstalNotifd.ClosedReason.CLOSED:
                reason = "closed"
            case _:
                reason = "undefined"
        logger.info(
            f"Notification {self.notification.get_id()} resolved with reason: {reason}"
        )
        self.set_reveal_child(False)


class NotificationPopup(WaylandWindow):
    def __init__(self, notification_server: NotificationServer):
        self._server = notification_server
        self.pop_up_list = []
        self._server.astal_notifd.connect("notified", self.on_new_notification)
        self.notifications = Box(
            style="padding:1px;",
            orientation="v",
            spacing=5,
        )
        super().__init__(
            anchor="top right",
            child=self.notifications,
            layer="overlay",
            all_visible=True,
            visible=True,
            exclusive=False,
        )
        self.show_all()

    def on_new_notification(self, astal_notifd: AstalNotifd.Notifd, id: int, idk):
        new_box = NotificationRevealer(astal_notifd.get_notification(id))
        self.notifications.add(
            Box(style="padding: 1px", children=new_box, h_align="end")
        )
        new_box.set_reveal_child(True)
