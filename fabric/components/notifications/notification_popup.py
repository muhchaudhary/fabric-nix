import gi
from services.notifications_astal_v2 import NotificationServer
from widgets.popup_window import PopupWindow

from fabric.widgets import Box, Button, Image, Label

gi.require_version("AstalNotifd", "0.1")
from gi.repository import AstalNotifd


class NotificationBox(Box):
    def __init__(self, notification: AstalNotifd.Notification, **kwargs):
        super().__init__(
            h_expand=True,
            name="notification-box",
            **kwargs,
        )
        self.notification = notification
        self.notification.connect("resolved", self.on_resolved)
        self.notification.connect("invoked", lambda *args: self.notification.dismiss())

        file_path = notification.get_image()
        file_path = notification.get_app_icon() if file_path is None else file_path
        # We have an icon name
        if file_path and file_path[0] != "/":
            self.notif_image = Image(
                icon_name=file_path + "-symbolic", style="color: black;", pixel_size=24
            )
        else:
            self.notif_image = Box(
                name="notification-image",
                style=f"background-image: url('{file_path}')",
            )

        self.action_buttons = Box(name="notification-action-buttons")
        for action in notification.get_actions():
            self.action_buttons.add_children(
                self.make_action_button(action.label, action.id)
            )

        self.add_children(self.notif_image) if self.notif_image else None
        self.add_children(
            Box(
                h_expand=True,
                orientation="v",
                children=[
                    Label(
                        notification.get_summary(),
                        h_align="start",
                        character_max_width=40,
                        ellipsization="end",
                    ),
                    Label(
                        notification.get_body(),
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

    def on_resolved(self, _, closed_reason: AstalNotifd.ClosedReason):
        reason = ""
        match closed_reason:
            case AstalNotifd.ClosedReason.EXPIRED:
                reason = ("expired")
            case AstalNotifd.ClosedReason.DISMISSED_BY_USER:
                reason = ("closed by user")
            case AstalNotifd.ClosedReason.CLOSED:
                reason = ("closed")
            case _:
                reason = ("undefined")
        print(f"Notification {self.notification.get_id()} resolved with reason: {reason}")
        self.destroy()


    def make_action_button(self, label: str, action_id: str) -> Button:
        action_button = Button(label=label, h_align="center", v_align="center")
        action_button.connect("clicked", lambda *_: self.notification.invoke(action_id))
        return action_button


class NotificationPopup(PopupWindow):
    def __init__(self, notification_server: NotificationServer):
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
        self.toggle_popup()

    def on_new_notification(
        self,
        notification_server: NotificationServer,
        notification: AstalNotifd.Notification,
    ):
        new_notif_box = NotificationBox(notification)
        self.notifications.add(new_notif_box)
        # self.popup_timeout()
