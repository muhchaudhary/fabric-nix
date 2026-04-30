from fabric.widgets.wayland import WaylandWindow
from fabric.widgets.box import Box
from fabric import Application
from fabric.notifications.service import Notifications
from fabric.widgets.label import Label
from fabric.widgets.shapes.corner import Corner
from fabric.widgets.scale import Scale
from fabric.widgets.revealer import Revealer
from fabric.widgets.image import Image
from fabric.widgets.button import Button
from gi.repository import GLib, GdkPixbuf
import urllib.parse


class NotificationsWindow(WaylandWindow):
    def __init__(self, **kwargs):
        super().__init__(layer="overlay", anchor="top right", **kwargs)
        self.notifications = Notifications()
        self.notifications_container = Box(orientation="v", name="container")
        self.left_corner = Corner(
            orientation="top-right", size=(12, 12), name="corner", v_align="start"
        )
        self.bottom_corner = Corner(
            orientation="top-right",
            size=(12, 12),
            name="corner",
            v_align="end",
            h_align="end",
        )
        self.intermediate = Box(
            children=[self.left_corner, self.notifications_container]
        )
        self.all = Box(
            children=[self.intermediate, self.bottom_corner], orientation="v"
        )
        self.children = self.all
        self.notifications.connect("notification_added", self.on_notification_added)

    def on_notification_added(self, _, id):
        notification = self.notifications.get_notification_from_id(id)

        new_notification = NotificationWidget(notification, name="notification_widget")
        new_notification_revealer = Revealer(
            child=new_notification,
            transition_type="slide-right",
            transition_duration=300,
        )

        black_box = Box(
            size=400,
            style="padding: 10px;",
            children=Box(
                h_expand=True,
                children=[
                    Box(h_expand=True, style="background-color: blue"),
                    new_notification_revealer,
                ],
            ),
            h_align="start",
        )

        black_box_revealer = Revealer(
            child=black_box,
            transition_type="slide-down",
            transition_duration=300,
        )
        black_box_revealer_container = Box(
            size=1,
            children=black_box_revealer,
            # h_align="end",
        )

        self.notifications_container.pack_end(
            black_box_revealer_container, False, False, 0
        )
        black_box_revealer.reveal()
        GLib.timeout_add(2000, lambda: new_notification_revealer.reveal())


class NotificationWidget(Box):
    def __init__(self, notification, **kwargs):
        super().__init__(
            size=(340, -1), orientation="v", spacing=5, v_expand=False, **kwargs
        )
        # Add icon to main_body
        self.main_body = Box(orientation="h", spacing=5)
        if notification.app_icon:
            self.app_icon = notification.app_icon
            self.app_icon_parsed = urllib.parse.unquote(
                urllib.parse.urlparse(self.app_icon).path
            )
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.app_icon_parsed)
                pixbuf2 = pixbuf.scale_simple(64, 64, GdkPixbuf.InterpType.BILINEAR)
            except Exception as e:
                print(f"Failed to load or scale icon: {e}")

            self.main_body.add(Image(pixbuf=pixbuf2))
        elif notification.image_pixbuf:
            self.image_pixbuf = notification.image_pixbuf
            self.main_body.add(
                Image(
                    pixbuf=self.image_pixbuf.scale_simple(
                        64, 64, GdkPixbuf.InterpType.BILINEAR
                    ),
                    v_align="start",
                )
            )

        # Create tex_body
        self.text_body = Box(orientation="v", spacing=5, h_expand=True)
        if notification.app_name:
            self.app_name = notification.app_name
        if notification.summary:
            self.summary = Label(
                label=notification.summary,
                name="summary",
                h_align="start",
                line_wrap="word-char",
                max_chars_width=30,
            )
            self.text_body.add(self.summary)
        if notification.body:
            self.body = Label(
                label=notification.body,
                name="body",
                h_align="start",
                line_wrap="word-char",
                max_chars_width=30,
            )
            self.text_body.add(self.body)

        # Add text body to main_body
        self.main_body.add(self.text_body)

        # Create button_body
        self.button_body = Box(orientation="v")
        # Close button
        self.close_button = Button(
            child=Label(label="X"), on_clicked=lambda: notification.close()
        )
        self.button_body.add(self.close_button)

        self.main_body.add(self.button_body)
        # Add main body to widget
        self.add(self.main_body)

        # Timer Logic
        self.timeout = 10
        if notification.timeout != -1:
            self.timeout = notification.timeout
        self.timer = Scale(
            h_expand=True,
            min_value=0.0,
            max_value=self.timeout,
            name="timer",
            v_align="baseline",
        )
        self.timer.set_sensitive(False)
        self.timer.set_value(self.timeout)
        self.add(self.timer)
        GLib.timeout_add(10, self.decrement_timer, notification)

    def decrement_timer(self, notification):
        self.timer.set_value(self.timer.get_value() - 0.01)
        if self.timer.get_value() == 0:
            notification.close()
            return False
        return True


if __name__ == "__main__":
    noticiations_window = NotificationsWindow()
    app = Application("notif", noticiations_window, open_inspector=True)
    app.set_stylesheet_from_file("test.css")
    app.run()
