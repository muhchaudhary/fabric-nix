from services.notifications_astal import Notification, NotificationServer
from widgets.popup_window import PopupWindow
from fabric.widgets import Box, Button, Label, Image


class NotificationBox(Box):
    def __init__(self, notification: Notification, **kwargs):
        super().__init__(
            h_expand=True,
            name="notification-box",
            **kwargs,
        )
        self.notification = notification
        self.notification.connect("closed", lambda _: self.destroy())

        file_path = notification.get_image_file_path()
        print(file_path)
        file_path = (
            notification.get_icon_file_path() if file_path is None else file_path
        )
        # We have an icon name
        if file_path[0] != "/":
            self.notif_image = Image(
                icon_name=file_path + "-symbolic", style="color: black;", pixel_size=24
            )
        else:
            self.notif_image = Box(
                name="notification-image",
                style=f"background-image: url('{file_path}')",
            )

        self.action_buttons = Box(name="notification-action-buttons")
        for action in notification.actions:
            self.action_buttons.add_children(
                self.make_action_button(action["label"], action["id"])
            )

        self.add_children(self.notif_image) if self.notif_image else None
        self.add_children(
            Box(
                h_expand=True,
                orientation="v",
                children=[
                    Label(
                        notification.summary,
                        h_align="start",
                        character_max_width=40,
                        ellipsization="end",
                    ),
                    Label(
                        notification.body,
                        h_align="start",
                        character_max_width=40,
                        ellipsization="end",
                    ),
                    self.action_buttons,
                ],
                h_align="start",
                v_align="start",
            ),
        )

    def make_action_button(self, label: str, action_id: str) -> Button:
        action_button = Button(label=label, h_align="center", v_align="center")
        action_button.connect("clicked", lambda *_: self.notification.invoke(action_id))
        return action_button


class NotificationPopup(PopupWindow):
    def __init__(self, notification_server: NotificationServer, **kwargs):
        self._server = notification_server
        self._server.connect("notification-received", self.on_new_notification)
        self.notifications = Box(
            orientation="v",
            spacing=5,
        )
        super().__init__(
            anchor="top right",
            transition_type="slide-left",
            transition_duration=350,
            child=self.notifications,
            timeout=5000,
        )

    def on_new_notification(
        self, notification_server: NotificationServer, notification: Notification
    ):
        new_notif_box = NotificationBox(notification)
        self.notifications.add(new_notif_box)
        self.popup_timeout()
