import gi
from services.notifications_astal_v2 import NotificationServer
from fabric.widgets import Box, Button, Image, Label, Revealer, WaylandWindow
from fabric.utils import invoke_repeater
from loguru import logger

gi.require_version("AstalNotifd", "0.1")
from gi.repository import AstalNotifd  # noqa: E402

# TODO: make a notification center
# TODO: group notifications by type


class NotificationBox(Revealer):
    def __init__(self, notification: AstalNotifd.Notification, **kwargs):
        self.notification_box = Box(
            h_expand=True,
            orientation="v",
            name="notification-box",
            spacing=5,
            **kwargs,
        )
        self.popup_timeout = 5000
        # Notification signals
        self.notification = notification
        self.notification.connect("resolved", self.on_resolved)
        self.notification.connect("invoked", lambda *args: self.notification.dismiss())

        # Grabbing the file path
        # TODO: find a better way to check if file path is a path or just an icon (app_icon can be path)
        # TODO: consider if using a custom cairo widget to display the image is better
        app_icon = notification.get_app_icon()
        self.app_icon_image = (
            Image(
                icon_name=app_icon + "-symbolic",
                style="color: white;",
                pixel_size=24,
            )
            if app_icon
            else Image(
                icon_name="dialog-information-symbolic",
                style="color: white;",
                pixel_size=24,
            )
        )

        self.action_buttons = Box(name="notification-action-buttons")
        for action in notification.get_actions():
            self.action_buttons.add_children(
                self.make_action_button(action.label, action.id)
            )
        self.notification_box.add_children(
            Box(
                children=[
                    self.app_icon_image,
                    Label(notification.get_app_name()),
                ]
            )
        )

        self.notification_box.add_children(
            [
                Box(
                    children=[
                        Box(
                            name="notification-image",
                            style=f"background-image: url('{notification.get_image() }')",
                        ),
                        Box(
                            orientation="v",
                            h_align="start",
                            v_align="start",
                            children=[
                                Label(
                                    notification.get_summary(),
                                    h_align="start",
                                    character_max_width=40,
                                    ellipsization="end",
                                    markup=True,
                                ),
                                Label(
                                    notification.get_body(),
                                    h_align="start",
                                    character_max_width=40,
                                    ellipsization="end",
                                    markup=True,
                                ),
                                self.action_buttons,
                            ],
                        ),
                    ]
                )
            ]
        )

        # self.add_children(

        # )
        super().__init__(
            children=self.notification_box,
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

    def make_action_button(self, label: str, action_id: str) -> Button:
        action_button = Button(label=label, h_align="center", v_align="center")
        action_button.connect("clicked", lambda *_: self.notification.invoke(action_id))
        return action_button


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
            children=self.notifications,
            layer="top",
            all_visible=True,
            visible=True,
            exclusive=False,
        )
        # self.revealer.connect(
        #     "notify::child-revealed",
        #     lambda revealer, *args: self.notifications.reset_children()
        #     if not revealer.get_child_revealed()
        #     else None,
        # )
        # self.toggle_popup()
        self.show_all()

    def on_new_notification(self, astal_notifd: AstalNotifd.Notifd, id: int):
        new_box = NotificationBox(astal_notifd.get_notification(id))
        self.notifications.add(
            Box(style="padding: 1px", children=new_box, h_align="end")
        )
        new_box.set_reveal_child(True)
