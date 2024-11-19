import math
import gi
from loguru import logger
from fabric_config.widgets.rounded_image import CustomImage

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

from gi.repository import Gtk
import cairo
from fabric_config.widgets.rotate_image import RotatableImage

gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import GdkPixbuf, Gtk, Gdk


# TODO: make a notification center
# TODO: group notifications by type


# Once again, This function is heavily inspired by Aylurs config for drag and drop :)
def createSurfaceFromWidget(widget: Gtk.Widget):
    alloc = widget.get_allocation()
    surface = cairo.ImageSurface(
        cairo.Format.ARGB32,
        alloc.width,
        alloc.height,
    )
    cr = cairo.Context(surface)
    cr.set_source_rgba(255, 255, 255, 0)
    cr.rectangle(0, 0, alloc.width, alloc.height)
    cr.fill()
    widget.draw(cr)
    return surface


class AnimationWindow(WaylandWindow):
    def __init__(self):
        self.fixed = Gtk.Fixed()
        super().__init__(
            anchor="top left bottom right",
            layer="top",
            child=Box(
                h_expand=True,
                v_expand=True,
                children=self.fixed,
            ),
            exclusivity="none",
            keyboard_mode="none",
            pass_through=True,
            visible=True,
            all_visible=True,
        )


# FIXME: I will make a global animations only window which will be used to call NON INTERACTABLE animations
animate_window = AnimationWindow()


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

    def get_icon(self, app_icon) -> Image:
        match app_icon:
            case str(x) if "file://" in x:
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

        # Save current Surface
        self.realize()
        alloc = self.get_allocation()
        last_frame = RotatableImage(
            pixbuf=Gdk.pixbuf_get_from_surface(
                createSurfaceFromWidget(self),
                0,
                0,
                alloc.width,
                alloc.height,
            )
        )

        animate_window.fixed.put(
            last_frame,  # Only works since its mapped to the top left...
            animate_window.get_allocated_width() - alloc.width,
            alloc.y,
        )
        animate_window.pass_through = True
        self.animate_move(
            last_frame,
            animate_window.get_allocated_width() - alloc.width,
            alloc.y,
            animate_window.get_allocated_width(),
            animate_window.get_allocated_height(),
        )

        self.transition_type = "slide-up"
        self.transition_duration = 500
        self.set_reveal_child(False)

    # FIXME: This is just for demonstrations purposes, use the property animator snppit instead
    # FIXME: This inculdes the random function I am using to show animations
    def animate_move(
        self, widget: RotatableImage, x: float, y: float, bound_x, bound_y
    ):
        frame_time = 10  # milliseconds per frame
        frame_time_s = frame_time / 1000  # convert to seconds for physics calculations

        # Initial position
        x = x
        y = y

        # Physics properties
        vx = -1000  # Velocity in x-direction (pixels per second)
        vy = 500  # Velocity in y-direction (pixels per second)
        ax = -5000  # Acceleration in x-direction (no acceleration here)
        ay = 1000  # Gravity-like acceleration (pixels per second^2)

        angle = 0

        def do_animate():
            nonlocal x, y, vx, vy, angle

            vx += ax * frame_time_s
            vy += ay * frame_time_s

            x += vx * frame_time_s
            y += vy * frame_time_s

            angle -= 5 * frame_time / 20
            angle = angle % 360
            widget.set_angle(angle)

            if (
                0 <= x + widget.get_allocated_width() / 2 <= bound_x
                and 0 <= y <= bound_y
            ):
                animate_window.fixed.move(
                    widget,
                    x,
                    y - widget.get_allocated_height() / 2,
                )
                # Check boundaries
                return True  # Continue animation
            else:
                widget.destroy()  # End animation
                return False
            return True

        invoke_repeater(frame_time, do_animate)

        invoke_repeater(10, do_animate)


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
