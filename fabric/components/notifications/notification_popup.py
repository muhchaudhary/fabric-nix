from fabric.widgets.wayland import Window
from fabric.widgets.revealer import Revealer
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from services.notifs import NotificationServer, Notification
from fabric.utils import invoke_repeater

from gi.repository import GLib


class NotificationBox(Box):
    def __init__(self, notification: Notification, **kwargs):
        notification.connect("closed", lambda _: self.destroy())

        self.notif_icon = Image()
        self.notif_image = Image()
        pixbuf = notification.get_image_pixbuf()
        pixbuf = notification.get_icon_pixbuf() if pixbuf is None else pixbuf
        self.notif_image.set_from_pixbuf(pixbuf) if pixbuf else None
        super().__init__(
            h_expand=True,
            children=[
                self.notif_image,
                Box(
                    h_expand=True,
                    orientation="v",
                    children=[
                        Label(notification.summary),
                        Label(notification.body),
                    ],
                    h_align="start",
                    v_align="start",
                ),
            ],
            **kwargs,
        )

        invoke_repeater(2000, lambda: [notification.close(), False][1])


class NotificationCenter(Window):
    def __init__(self, notification_server: NotificationServer, **kwargs):
        self._server = notification_server

        self._server.connect("notification-received", self.on_new_notification)
        self.notifications = Box(
            orientation="v",
            style="padding:1px; background-color: red;",
            spacing=5,
        )
        self.notif_dash = Revealer(
            h_expand=True,
            children=self.notifications,
            transition_duration=350,
            transition_type="slide-left",
        )
        super().__init__(
            layer="overlay",
            anchor="top right",
            margin="10px 0px 10px 0px",
            children=Box(style="padding: 1px;", children=self.notif_dash),
            all_visible=False,
            visible=False,
            exclusive=False,
            **kwargs,
        )
        self.show()

    def on_new_notification(
        self, notification_server: NotificationServer, notification_id: int
    ):
        new_notif_box = NotificationBox(
            notification_server.get_notification_for_id(notification_id),
        )

        self.notifications.add(new_notif_box)
        self.notif_dash.set_reveal_child(True)