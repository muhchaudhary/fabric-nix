from fabric import Signal
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
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow
from loguru import logger

from fabric_config.snippits.animator import Animator
from fabric_config.widgets.rounded_image import CustomImage

import gi

gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gtk


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
            # style="background-color: red;",
            children=[
                CenterBox(
                    name="notification-title",
                    spacing=0,
                    start_children=[
                        self.get_icon(notification.app_icon),
                        Label(
                            str(notification.app_name),
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
                                    label=(
                                        notification.summary[:30]
                                        + (notification.summary[30:] and "...")
                                    ),
                                    line_wrap="word-char",
                                    max_chars_width=40,
                                    h_align="start",
                                    style="font-weight: 900",
                                ),
                                Label(
                                    label=(
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

    def get_icon(self, app_icon) -> Image:
        match app_icon:
            case str(x) if x.startswith("file://"):
                return Image(
                    name="notification-icon",
                    image_file=app_icon[7:],
                    size=24,
                )
            case str(x) if len(x) > 0 and "/" == x[0]:
                return Image(
                    name="notification-icon",
                    image_file=app_icon,
                    size=24,
                )
            case _:
                return Image(
                    name="notification-icon",
                    icon_name=app_icon if app_icon else "dialog-information-symbolic",
                    size=24,
                )


class NotificationPopup(WaylandWindow):
    def __init__(self):
        self._server = Notifications()
        self.notifications = Box(
            v_expand=True,
            h_expand=True,
            # style="margin: 1px; transition: all 1.5s ease;",
            size=1,
            orientation="v",
            spacing=5,
        )
        # self.revealer = Revealer(child=self.notifications, transition_type="slide-left")
        self._server.connect("notification-added", self.on_new_notification)
        # self._server.connect("notification-removed", self.on_notification_removed)
        self._server.connect("notification-closed", self.on_notification_closed)

        super().__init__(
            anchor="top right",
            child=self.notifications,
            layer="overlay",
            all_visible=True,
            visible=True,
            exclusive=False,
        )
        self.show_all()

    def on_notification_closed(self, fabric_notif, id, reason):
        pass

    def on_new_notification(self, fabric_notif, id):
        new_box = NotificationBox(
            notification=self._server.get_notification_from_id(id)
        )
        rev = Revealer(
            child=new_box, transition_type="slide-left", transition_duration=1000
        )

        def do_add():
            self.notifications.add(
                Box(children=[Box(h_expand=True, style="background-color: blue"), rev])
            )
            # rev.set_reveal_child(True)

        do_add()

        new_box.connect("size-allocate", lambda *args: rev.set_reveal_child(True))

        # self.revealer.set_reveal_child(True)
        # new_box.grab_offscreen(self.notifications.get_allocation())
        # new_box.set_reveal_child(True)
