import math
import time
from collections.abc import Callable

import cairo
import gi
from fabric.notifications.service import Notification
from fabric.utils import get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow

from fabric_config import config
from fabric_config.services.notifications import URGENCY_CRITICAL, hint
from fabric_config.snippits.animator import Animator
from fabric_config.utils.play_audio import play_sound
from fabric_config.widgets.notification_card import NotificationCard

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

DEFAULT_TIMEOUT_MS = 5000
MAX_POPUPS = 4
# progress bar / countdown update interval
TICK_MS = 33
SOUND_PATH = get_relative_path("../assets/sounds/notification.mp3")


class AnimationWindow(WaylandWindow):
    """
    A full-screen, click-through overlay that the cards fly in and out on.
    Only mapped while something is on it.
    """

    def __init__(self):
        self.draw_surfaces = []
        self.drawing_area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self._shown_on: Gdk.Monitor | None = None

        super().__init__(
            title="fabric-toast",
            anchor="top left bottom right",
            layer="overlay",
            child=Box(h_expand=True, v_expand=True, children=self.drawing_area),
            exclusivity="none",
            keyboard_mode="none",
            pass_through=True,
            visible=False,
        )
        self.drawing_area.show()
        self.drawing_area.connect("draw", self.on_draw)

    def prepare(self, monitor: Gdk.Monitor | None) -> tuple[int, int]:
        """Map the window (on `monitor`) if it isn't, and return its size."""
        if not self.get_visible():
            if monitor is not None:
                self.monitor = monitor
                self._shown_on = monitor
            self.show()
        # it covers the whole monitor. Don't ask GTK: right after showing it,
        # the allocation is a 200x200 default until the compositor configures it
        # (animations only tick once it's mapped anyway)
        display = Gdk.Display.get_default()
        # (a GdkDisplay is falsy: compare with None)
        target = self._shown_on or (
            display.get_monitor(0) if display is not None else None
        )
        if target is None:
            return self.get_allocated_width(), self.get_allocated_height()
        geometry = target.get_geometry()
        return geometry.width, geometry.height

    def move_surface(self, surface: cairo.Surface, x, y, angle, global_rotate=False):
        for i in range(len(self.draw_surfaces)):
            if self.draw_surfaces[i][0] == surface:
                self.draw_surfaces[i] = (surface, x, y, angle, global_rotate)
                self.drawing_area.queue_draw()

    def add_surface(self, surface: cairo.Surface, x, y, angle, global_rotate=False):
        self.draw_surfaces.append((surface, x, y, angle, global_rotate))
        self.drawing_area.queue_draw()

    def destroy_surface(self, surface: cairo.Surface):
        for i in range(len(self.draw_surfaces)):
            if self.draw_surfaces[i][0] == surface:
                del self.draw_surfaces[i]
                self.drawing_area.queue_draw()
                break
        if not self.draw_surfaces:
            self.hide()

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


def _snapshot(widget: Gtk.Widget) -> cairo.ImageSurface:
    alloc = widget.get_allocation()
    surface = cairo.ImageSurface(
        cairo.FORMAT_ARGB32, max(alloc.width, 1), max(alloc.height, 1)
    )
    widget.draw(cairo.Context(surface))
    return surface


def _monitor_of(widget: Gtk.Widget) -> Gdk.Monitor | None:
    window = widget.get_window()
    display = Gdk.Display.get_default()
    if window is None or display is None:  # (a GdkDisplay is falsy)
        return None
    return display.get_monitor_at_window(window)


def _timeout_ms(notification: Notification) -> int | None:
    """How long the popup stays up; None for until dismissed."""
    if notification.urgency >= URGENCY_CRITICAL or notification.timeout == 0:
        return None
    return notification.timeout if notification.timeout > 0 else DEFAULT_TIMEOUT_MS


class NotificationRevealer(Revealer):
    """
    One popup. It flies in, counts down (paused while hovered) and flies out.
    Running out of time only hides the popup: the notification stays in the
    notification center (unless it's marked transient).
    """

    def __init__(
        self,
        notification: Notification,
        on_hidden: Callable[["NotificationRevealer"], None],
    ):
        self.notification = notification
        self.leaving = False
        self._on_hidden = on_hidden
        self._timer: int | None = None
        self._timeout_ms: int | None = None
        self._remaining_ms = 0.0
        self._last_tick = 0.0
        self._fly_in_anim: Animator | None = None
        self._fly_in_surface: cairo.ImageSurface | None = None

        self.card = self._make_card(notification)
        self._holder = Box(style="margin: 1px 0px 1px 1px;")

        super().__init__(
            child=self._holder,
            transition_duration=0,
            transition_type="crossfade",
        )
        self.connect(
            "notify::child-revealed",
            lambda *_: (
                self.destroy()
                if self.leaving and not self.get_child_revealed()
                else None
            ),
        )

    def _make_card(self, notification: Notification) -> NotificationCard:
        return NotificationCard(
            notification, show_progress=True, on_click=self.dismiss_popup
        )

    # ---- countdown -------------------------------------------------------

    def _start_timer(self):
        self._stop_timer()
        self._timeout_ms = _timeout_ms(self.notification)
        self.card.progress_bar.set_visible(self._timeout_ms is not None)
        if self._timeout_ms is None:
            return
        self.card.progress_bar.set_fraction(1.0)
        self._remaining_ms = self._timeout_ms
        self._last_tick = time.monotonic()
        self._timer = GLib.timeout_add(TICK_MS, self._tick)

    def _stop_timer(self):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def _tick(self) -> bool:
        now = time.monotonic()
        elapsed_ms = (now - self._last_tick) * 1000
        self._last_tick = now
        if self.card.hovered or not self._timeout_ms:
            return True
        self._remaining_ms -= elapsed_ms
        if self._remaining_ms <= 0:
            self._timer = None
            if hint(self.notification, "transient"):
                # not meant to be kept: close it (which flies this out)
                self.notification.close("expired")
            else:
                self.dismiss_popup()
            return False
        self.card.progress_bar.set_fraction(self._remaining_ms / self._timeout_ms)
        return True

    # ---- content ---------------------------------------------------------

    def replace(self, notification: Notification):
        """Show `notification` in place of this one (same id chain, new content)."""
        self.notification = notification
        old = self.card
        self.card = self._make_card(notification)
        self._holder.remove(old)
        old.destroy()
        self._holder.add(self.card)
        self.card.show_all()
        if self.get_child_revealed():
            self._start_timer()

    def dismiss_popup(self, *_):
        """Hide the popup but keep the notification."""
        self.fly_out()

    # ---- animations ------------------------------------------------------

    def fly_in(self, monitor: Gdk.Monitor | None, y: int):
        # lay the card out offscreen to draw the flying copy, then move it in
        offscreen = Gtk.OffscreenWindow()
        offscreen.add(self.card)
        offscreen.show_all()
        surface = _snapshot(self.card)
        offscreen.remove(self.card)
        offscreen.destroy()
        self._holder.add(self.card)
        self.card.show_all()

        width, _ = animate_window.prepare(monitor)
        self._fly_in_surface = surface
        animate_window.add_surface(surface, width + 1, y, 0)

        def step(p: Animator, *_):
            tilt = p.value if p.value < p.max_value / 2 else p.max_value - p.value
            animate_window.move_surface(
                surface, width - p.value + 1, y + 2, (tilt / 30) % 360, True
            )

        def finished(*_):
            animate_window.destroy_surface(surface)
            self._fly_in_surface = None
            self._fly_in_anim = None
            if self.leaving:
                return
            self.set_reveal_child(True)
            self._start_timer()

        self._fly_in_anim = Animator(
            bezier_curve=(0.42, 0, 0.58, 1),
            duration=1,
            min_value=0,
            max_value=surface.get_width(),
            tick_widget=animate_window.drawing_area,
            notify_value=step,
        )
        self._fly_in_anim.connect("finished", finished)
        self._fly_in_anim.play()

    def fly_out(self):
        if self.leaving:
            return
        self.leaving = True
        self._stop_timer()
        self._on_hidden(self)

        if not self.get_child_revealed():
            # still flying in: just stop
            if self._fly_in_anim is not None:
                self._fly_in_anim.stop()
            if self._fly_in_surface is not None:
                animate_window.destroy_surface(self._fly_in_surface)
            self.destroy()
            return

        surface = _snapshot(self.card)
        y = self.get_allocation().y
        self._start_fly_out(surface, y)

        self.transition_type = "slide-up"
        self.transition_duration = 500
        self.set_reveal_child(False)

    def _start_fly_out(self, surface: cairo.ImageSurface, y: float):
        bound_x, bound_y = animate_window.prepare(self._monitor())
        x = bound_x - surface.get_width()
        animate_window.add_surface(surface, x, y, 0)

        def step(p: Animator, *_):
            nonlocal x, y
            angle = -p.value % 360
            x -= p.value / 4
            y += p.value / 6
            if 0 <= x + surface.get_width() / 2 <= bound_x and 0 <= y <= bound_y:
                animate_window.move_surface(surface, x, y, angle)
            else:
                animate_window.destroy_surface(surface)
                GLib.idle_add(anim.stop)

        anim = Animator(
            bezier_curve=(0, 0, 1, 1),
            duration=5,
            min_value=0,
            max_value=(360 * 5),
            tick_widget=animate_window.drawing_area,
            notify_value=step,
            on_finished=lambda *_: animate_window.destroy_surface(surface),
        )
        anim.play()

    def _monitor(self) -> Gdk.Monitor | None:
        return _monitor_of(self)


class NotificationPopup(WaylandWindow):
    def __init__(self):
        self.center = config.notifications
        # showing popups by notification id, oldest first
        self._popups: dict[int, NotificationRevealer] = {}
        self.notifications = Box(
            v_expand=True,
            h_expand=True,
            style="margin: 1px 0px 1px 1px;",
            orientation="v",
            spacing=5,
        )
        self.center.connect("notification-added", lambda _, n: self._show(n))
        self.center.connect("notification-replaced", self._on_replaced)
        self.center.connect("notification-removed", self._on_removed)

        super().__init__(
            title="fabric-toast",
            anchor="top right",
            child=self.notifications,
            layer="overlay",
            all_visible=True,
            visible=True,
        )

    def _show(self, notification: Notification):
        if not self.center.should_popup(notification):
            return
        if not self.center.dnd and not hint(notification, "suppress-sound"):
            play_sound(SOUND_PATH)

        popup = NotificationRevealer(notification, on_hidden=self._forget)
        self._popups[notification.id] = popup
        self.notifications.add(popup)
        popup.show()
        # it lands at the bottom of the stack
        popup.fly_in(self._monitor(), self.notifications.get_allocated_height())
        self._limit()

    def _limit(self):
        # make room by hiding the oldest; critical ones stay until dismissed
        popups = list(self._popups.values())
        excess = len(popups) - MAX_POPUPS
        for popup in popups:
            if excess <= 0:
                break
            if not popup.card.hovered and popup.notification.urgency < URGENCY_CRITICAL:
                popup.dismiss_popup()
                excess -= 1

    def _forget(self, popup: NotificationRevealer):
        if self._popups.get(popup.notification.id) is popup:
            del self._popups[popup.notification.id]

    def _on_replaced(self, _, old_id: int, notification: Notification):
        popup = self._popups.pop(old_id, None)
        if popup is None:
            self._show(notification)
            return
        popup.replace(notification)
        self._popups[notification.id] = popup

    def _on_removed(self, _, notification_id: int):
        popup = self._popups.pop(notification_id, None)
        if popup is not None:
            popup.fly_out()

    def _monitor(self) -> Gdk.Monitor | None:
        return _monitor_of(self)
