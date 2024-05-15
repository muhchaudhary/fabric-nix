from fabric.widgets.wayland import Window
from fabric.widgets.revealer import Revealer
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from services.notifs import NotificationServer, Notification
from fabric.utils import invoke_repeater


class NotificationRevealer(Revealer):
    def __init__(self, notification: Notification, **kwargs):
        notification.connect("closed", lambda _: self.destroy())

        self.notif_icon = Image()
        self.notif_image = Image()
        image_pixbuf = notification.get_image()
        self.notif_image.set_from_pixbuf(image_pixbuf) if image_pixbuf else None
        self.notif_image.set_pixel_size(10)
        self.actual_box = Box(
            all_visible=True,
            style="background-color: black; padding: 1px; min-width: 300px;",
            children=[
                self.notif_image,
                Box(
                    orientation="v",
                    children=[
                        Label("WTFDSJKFDSHLFHDSFLSDFDSFKDSHFDSFSDFJKDSSFD"),
                        Label(notification.summary),
                        Label(notification.body),
                    ],
                ),
            ],
        )
        super().__init__(
            transition_duration=100,
            transition_type="slide-left",
            children=self.actual_box,
            **kwargs,
        )

        invoke_repeater(8000, lambda: [notification.close(), False][1])


class NotificationCenter(Window):
    def __init__(self, notification_server: NotificationServer, **kwargs):
        self._server = notification_server

        self._server.connect("notification-received", self.on_new_notification)
        self.notifications = Box(
            orientation="v",
            style="padding: 30px; background-color: black;",
            spacing=5,
        )
        super().__init__(
            layer="overlay",
            anchor="top right",
            margin="10px 0px 10px 0px",
            children=Box(style="padding:1px;", children=self.notifications),
            visible=True,
            all_visible=False,
            exclusive=False,
            *kwargs,
        )
        self.show_all()

    def on_new_notification(
        self, notification_server: NotificationServer, notification_id: int
    ):
        new_notif_box = NotificationRevealer(
            notification_server.get_notification_for_id(notification_id)
        )
        self.notifications.add(Box(style="padding: 1px", children=new_notif_box))
        new_notif_box.set_child_visible(True)
