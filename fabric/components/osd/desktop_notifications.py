from fabric.widgets.wayland import Window
from fabric.widgets.revealer import Revealer
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from services.notifs import NotificationServer, Notification
from fabric.utils import invoke_repeater


class NotificationBox(Box):
    def __init__(self, notification: Notification, **kwargs):
        super().__init__(style="padding: 20px;", **kwargs)
        notification.connect("closed", lambda _: self.destroy())

        self.notif_summary = Label(notification.summary)
        self.notif_icon = Image()
        print(notification.hints.keys(), notification.app_icon)
        self.notif_image = Image()
        image_pixbuf = notification.get_image()
        self.notif_image.set_from_pixbuf(image_pixbuf) if image_pixbuf else None
        self.notif_image.set_pixel_size(10)
        self.add_children(
            [
                self.notif_image,
                Box(
                    orientation="v",
                    children=[
                        self.notif_summary,
                        Label(notification.body),
                    ],
                ),
            ]
        )
        invoke_repeater(8000, lambda: [notification.close(), False][1])


class NotificationCenter(Window):
    def __init__(self, notification_server: NotificationServer, **kwargs):
        self._server = notification_server

        self._server.connect("notification-received", self.on_new_notification)
        self.notifications = Box(
            style="background-color: black; ",
        )
        self.notif_revealer = Revealer(
            transition_type="slide-left",
            transition_duration=500,
            children=self.notifications,
        )
        super().__init__(
            layer="overlay",
            anchor="top right",
            margin="10px 0px 10px 0px",
            exclusive=True,
            children=Box(style="padding:1px;", children=self.notif_revealer),
            visible=True,
        )
        self.show_all()

    def on_new_notification(
        self, notification_server: NotificationServer, notification_id: int
    ):
        notification: Notification = notification_server.get_notification_for_id(
            notification_id
        )
        new_notif_box = NotificationBox(notification)
        self.notifications.add(new_notif_box)
        self.notif_revealer.set_reveal_child(True)
