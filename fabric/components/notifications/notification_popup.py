import gi
from loguru import logger
from widgets.rounded_image import CustomImage

from fabric.notifications.service import (
    Notification,
    NotificationAction,
    NotificationCloseReason,
    Notifications,
)
from fabric.utils import invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow

from fabric.widgets.overlay import Overlay
from fabric.widgets.circularprogressbar import CircularProgressBar

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf

# TODO: make a notification center
# TODO: group notifications by type


class ActionButton(Button):
    def __init__(
        self, action: NotificationAction, action_number: int, total_actions: int
    ):
        self.action = action
        super().__init__(
            label=action.label,
            h_expand=True,
            on_clicked=self.on_clicked,
        )
        if action_number == 0:
            self.add_style_class("start-action")
        elif action_number == total_actions - 1:
            self.add_style_class("end-action")
        else:
            self.add_style_class("middle-action")

    def on_clicked(self, *_):
        self.action.invoke()
        self.action.parent.close("dismissed-by-user")


class NotificationBox(Box):
    def __init__(self, notification: Notification):
        self.progress_timeout = CircularProgressBar(
            name="notification-title-circular-progress-bar",
            size=35,
            min_value=0,
            max_value=1,
            radius_color=True,
        )
        super().__init__(
            name="notification-box",
            orientation="v",
            children=[
                CenterBox(
                    name="notification-title",
                    spacing=0,
                    start_children=[
                        Image(
                            name="notification-icon",
                            image_file=notification.app_icon[7:],
                            size=24,
                        )
                        if "file://" in notification.app_icon
                        else Image(
                            name="notification-icon",
                            icon_name=notification.app_icon
                            if notification.app_icon
                            else "dialog-information-symbolic",
                            icon_size=24,
                        ),
                        Label(
                            notification.app_name,
                            h_align="start",
                            style="font-weight: 900;",
                        ),
                    ],
                    end_children=[
                        Overlay(
                            child=self.progress_timeout,
                            overlays=Button(
                                name="notification-title-button",
                                image=Image(
                                    icon_name="window-close-symbolic", icon_size=15
                                ),
                                on_clicked=lambda *_: notification.close(
                                    "dismissed-by-user"
                                ),
                            ),
                        ),
                    ],
                ),
                Box(
                    name="notification-content",
                    spacing=10,
                    children=[
                        Box(
                            name="notification-image",
                            children=CustomImage(
                                pixbuf=notification.image_pixbuf.scale_simple(
                                    75, 75, GdkPixbuf.InterpType.BILINEAR
                                )
                                if notification.image_pixbuf
                                else None
                            ),
                        ),
                        Box(
                            orientation="v",
                            children=[
                                Label(
                                    markup=(
                                        notification.summary[:30]
                                        + (notification.summary[30:] and "...")
                                    ),
                                    line_wrap="word-char",
                                    max_chars_width=40,
                                    h_align="start",
                                    style="font-weight: 900",
                                ),
                                Label(
                                    markup=(
                                        notification.body[:120]
                                        + (notification.body[120:] and "...")
                                    ),
                                    line_wrap="word-char",
                                    max_chars_width=40,
                                    h_align="start",
                                ),
                            ],
                        ),
                    ],
                ),
                Box(name="notification-seperator", h_expand=True)
                if notification.actions
                else Box(),
                Box(
                    name="notification-action-buttons",
                    children=[
                        ActionButton(action, i, len(notification.actions))
                        for i, action in enumerate(notification.actions)
                    ],
                    h_expand=True,
                ),
            ],
        )


class NotificationRevealer(Revealer):
    def __init__(self, notification: Notification, **kwargs):
        self.popup_timeout = 5000
        self.not_box = NotificationBox(notification)
        self.notification = notification
        self.not_box.progress_timeout.max_value = self.popup_timeout
        super().__init__(
            child=Box(style="margin: 1px 0px 1px 1px;", children=self.not_box),
            transition_duration=500,
            transition_type="crossfade",
        )

        self.animate_popup_timeout()
        self.connect(
            "notify::child-revealed",
            lambda *args: self.destroy() if not self.get_child_revealed() else None,
        )

        notification.connect("closed", self.on_resolved)

    def animate_popup_timeout(self):
        time = self.popup_timeout

        def do_animate():
            nonlocal time
            self.not_box.progress_timeout.value = time
            if not self.child_revealed:
                return False
            if time <= 0:
                self.set_reveal_child(False)
                self.notification.close("expired")
                return False
            time -= 10
            return True

        invoke_repeater(10, do_animate)

    def on_resolved(self, notification, closed_reason: NotificationCloseReason):
        logger.info(
            f"Notification {notification.id} resolved with reason: {closed_reason}"
        )
        self.set_reveal_child(False)


class NotificationPopup(WaylandWindow):
    def __init__(self):
        self._server = Notifications()
        self.notifications = Box(
            v_expand=True,
            h_expand=True,
            style="margin: 1px 0px 1px 1px;",
            orientation="v",
            spacing=5,
        )
        self._server.connect("notification-added", self.on_new_notification)
        # self._server.connect("notification-removed", self.on_notification_removed)
        # self._server.connect("notification-closed", self.on_notification_closed)

        super().__init__(
            anchor="top right",
            child=self.notifications,
            layer="overlay",
            all_visible=True,
            visible=True,
            exclusive=False,
        )

    def on_new_notification(self, fabric_notif, id):
        new_box = NotificationRevealer(fabric_notif.get_notification_from_id(id))
        self.notifications.add(new_box)
        new_box.set_reveal_child(True)
