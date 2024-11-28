import math
import time

import cairo
import gi
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
from gi.repository import Gtk
from loguru import logger

from fabric_config.snippits.animator import Animator
from fabric_config.widgets.rounded_image import CustomImage

gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

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
        self.draw_surfaces = []
        self.drawing_area = Gtk.DrawingArea()
        self.fixed = Gtk.Fixed()
        self.last_update_time = time.time()

        super().__init__(
            anchor="top left bottom right",
            layer="top",
            child=Box(
                h_expand=True,
                v_expand=True,
                # children=self.fixed,
                children=self.drawing_area,
            ),
            exclusivity="none",
            keyboard_mode="none",
            pass_through=True,
            visible=True,
            all_visible=True,
        )
        self.drawing_area.set_size_request(
            self.get_allocated_width(), self.get_allocated_height()
        )
        self.drawing_area.connect("draw", self.on_draw)

    def move_surface(self, surface: cairo.Surface, x, y, angle, global_rotate=False):
        for i in range(len(self.draw_surfaces)):
            if self.draw_surfaces[i][0] == surface:
                self.draw_surfaces[i] = (surface, x, y, angle, global_rotate)
                self.drawing_area.queue_draw()

    def add_surface(self, surface: cairo.Surface, x, y, angle, global_rotate=False):
        self.drawing_area.set_size_request(
            self.get_allocated_width(), self.get_allocated_height()
        )
        self.draw_surfaces.append((surface, x, y, angle, global_rotate))
        self.drawing_area.queue_draw()

    def destroy_surface(self, surface: cairo.Surface):
        for i in range(len(self.draw_surfaces)):
            if self.draw_surfaces[i][0] == surface:
                del self.draw_surfaces[i]
                self.drawing_area.queue_draw()
                return

    def on_draw(self, _, cr: cairo.Context):
        for surface, x, y, angle, global_rotate in self.draw_surfaces:
            width = surface.get_width()
            height = surface.get_height()
            cr.save()
            if global_rotate:
                cr.rotate(angle * math.pi / 180)
                cr.set_source_surface(surface, x, y)
            else:
                cr.translate(x, y)
                cr.translate(width / 2, height / 2)
                cr.rotate(angle * math.pi / 180)
                cr.set_source_surface(surface, -width / 2, -height / 2)
            cr.paint()

            cr.restore()


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
    @Signal
    def animation_done(self, is_done: bool) -> bool: ...

    def __init__(self, notification: Notification, **kwargs):
        self.popup_timeout = 5000
        self.not_box = NotificationBox(notification)
        self.notification = notification
        self.not_box.progress_timeout.max_value = self.popup_timeout

        super().__init__(
            child=Box(style="margin: 1px 0px 1px 1px;", children=self.not_box),
            transition_duration=0,
            transition_type="crossfade",
        )

        self.connect(
            "notify::child-revealed",
            lambda *args: self.destroy() if not self.get_child_revealed() else None,
        )
        self.connect(
            "animation-done",
            lambda *_: [self.set_reveal_child(True), self.animate_popup_timeout()],
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
                self.notification.close("expired")
                return False
            time -= 10
            return True

        invoke_repeater(10, do_animate)

    def on_resolved(self, notification, closed_reason: NotificationCloseReason):
        logger.info(
            f"Notification {notification.id} resolved with reason: {closed_reason}"
        )

        alloc = self.get_allocation()

        x = animate_window.get_allocated_width() - alloc.width
        y = alloc.y
        surface = self.offscreen_surface
        bound_x = animate_window.get_allocated_width()
        bound_y = animate_window.get_allocated_height()

        def do_animate_animator(p: Animator, *_):
            nonlocal x, y

            angle = -p.value % 360
            x -= p.value / 4
            y += p.value / 6

            if 0 <= x + surface.get_width() / 2 <= bound_x and 0 <= y <= bound_y:
                animate_window.move_surface(surface, x, y, angle)
            else:
                animate_window.destroy_surface(self.offscreen_surface)

        anim = Animator(
            bezier_curve=(0, 0, 1, 1),
            duration=5,
            min_value=0,
            max_value=(360 * 5),
            tick_widget=animate_window.drawing_area,
            notify_value=do_animate_animator,
            on_finished=lambda *_: animate_window.destroy_surface(surface),
        )
        anim.play()

        self.transition_type = "slide-up"
        self.transition_duration = 500
        self.set_reveal_child(False)

    def grab_offscreen(self, box_allocation: Gdk.Rectangle):
        offscreen = Gtk.OffscreenWindow()
        offscreen.get_style_context().add_class(Gtk.STYLE_CLASS_DND)
        frame = Gtk.Frame()

        nb = NotificationBox(self.notification)
        frame.add(nb)
        frame.show_all()

        offscreen.add(frame)
        offscreen.show()
        alloc = frame.get_allocation()
        frame.draw(cairo.Context(offscreen.get_surface()))
        self.offscreen_surface = offscreen.get_surface()

        animate_window.add_surface(
            self.offscreen_surface,
            animate_window.get_allocated_width() + 1,
            (alloc.y + box_allocation.height),
            0,
        )
        animate_window.pass_through = True
        anim_alloc = animate_window.get_allocation()

        def do_animate_animator(p: Animator, *_):
            animate_window.move_surface(
                self.offscreen_surface,
                anim_alloc.width - p.value + 1,
                (alloc.y + box_allocation.height) + 2,
                (p.value / 30) % 360
                if p.value < p.max_value // 2
                else ((p.max_value - p.value) / 30) % 360,
                True,
            )

        def on_anim_finished(*_):
            # Hide surface
            animate_window.move_surface(
                self.offscreen_surface,
                animate_window.get_allocated_width(),
                animate_window.get_allocated_height(),
                0,
            )
            self.emit("animation-done", True)
            # last_frame.destroy()

        anim = Animator(
            bezier_curve=(0.42, 0, 0.58, 1),
            duration=1,
            min_value=0,
            max_value=alloc.width,
            tick_widget=animate_window.drawing_area,
            notify_value=do_animate_animator,
        )
        anim.play()
        anim.connect("finished", on_anim_finished)

        offscreen.remove(frame)
        frame.destroy()
        offscreen.destroy()

        # self.emit("animation_done", True)


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
        new_box.grab_offscreen(self.notifications.get_allocation())
        # new_box.set_reveal_child(True)
