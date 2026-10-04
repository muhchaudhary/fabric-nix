import html
import os
import re
import time
from collections.abc import Callable

import gi
from fabric.notifications.service import Notification, NotificationAction
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from loguru import logger

from fabric_config.services.notifications import URGENCY_CRITICAL, hint
from fabric_config.utils.icon_resolver import get_icon_resolver
from fabric_config.utils.uri import file_uri_to_path
from fabric_config.widgets.rounded_cover_image import RoundedCoverImage

gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango  # noqa: E402

IMAGE_SIZE = 48
# images are only ever shown small; don't keep a full-size screenshot around
IMAGE_LOAD_SIZE = 256
DEFAULT_ACTION = "default"


def relative_time(timestamp: float) -> str:
    seconds = time.time() - timestamp
    if seconds < 60:
        return "now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    return time.strftime("%b %d", time.localtime(timestamp))


def notification_image(notification: Notification) -> GdkPixbuf.Pixbuf | None:
    """The notification's image (not its app icon), if it has a loadable one."""
    try:
        if notification.image_pixmap:
            return notification.image_pixmap.as_pixbuf()
        if path := notification.image_file:
            if path.startswith("file://"):
                path = file_uri_to_path(path)
            # image-path may also be an icon name (notify-send -i puts it
            # there); app_icon() shows that one
            if not os.path.isabs(path):
                return None
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(
                path, IMAGE_LOAD_SIZE, IMAGE_LOAD_SIZE, True
            )
    except Exception as e:
        logger.warning(f"[Notifications] Couldn't load image: {e}")
    return None


def app_icon(notification: Notification, size: int) -> Image:
    icon = notification.app_icon or ""
    image = notification.image_file or ""
    if (
        not icon
        and image
        and not image.startswith("file://")
        and not os.path.isabs(image)
    ):
        icon = image
    if icon.startswith("file://"):
        icon = file_uri_to_path(icon)
    if not icon:
        # no icon given: find one from the sender's desktop entry or name
        app_id = str(hint(notification, "desktop-entry") or notification.app_name)
        icon = get_icon_resolver().get_icon_name(app_id) if app_id else ""

    if os.path.isabs(icon):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(icon, size, size)
            return Image(pixbuf=pixbuf, name="notification-icon")
        except GLib.Error:
            icon = ""
    if not icon or not Gtk.IconTheme.get_default().has_icon(icon):
        icon = "dialog-information-symbolic"
    return Image(icon_name=icon, icon_size=size, name="notification-icon")


_TAG_RE = re.compile(r"<(/?)([a-zA-Z]+)([^>]*)>")
_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']*)""")
_SIMPLE_TAGS = {"b", "i", "u"}


def _escape(text: str) -> str:
    # bodies are often sent unescaped, or with HTML entities; normalise both
    return GLib.markup_escape_text(html.unescape(text), -1)


def body_markup(text: str) -> str:
    """
    Pango markup for a notification body (the spec allows <b> <i> <u> <a> and
    <img>). Keeps the markup it can show, escapes everything else, and falls
    back to plain text if the result still doesn't parse.
    """
    out: list[str] = []
    open_links: list[str] = []
    pos = 0
    for match in _TAG_RE.finditer(text):
        out.append(_escape(text[pos : match.start()]))
        pos = match.end()
        closing, tag, attrs = match.groups()
        tag = tag.lower()
        if tag in _SIMPLE_TAGS:
            out.append(f"<{closing}{tag}>")
        elif tag == "br":
            out.append("\n")
        elif tag == "a":
            if closing:
                if open_links:
                    out.append(f"</{open_links.pop()}>")
            elif href := _HREF_RE.search(attrs):
                out.append(f'<a href="{_escape(href.group(1))}">')
                open_links.append("a")
            else:
                out.append("<span>")
                open_links.append("span")
        # anything else (<img>, unknown tags) is dropped
    out.append(_escape(text[pos:]))
    markup = "".join(out)

    try:
        # Pango doesn't know <a> (GtkLabel handles it), so check without them
        Pango.parse_markup(re.sub(r"</?a\b[^>]*>", "", markup), -1, "\0")
    except GLib.Error:
        return _escape(_TAG_RE.sub("", text))
    return markup


def _wrapping_label(markup: str, name: str, lines: int) -> Label:
    label = Label(markup=markup, name=name, h_align="start", max_chars_width=38)
    label.set_xalign(0)
    label.set_line_wrap(True)
    label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    label.set_lines(lines)
    label.set_ellipsize(Pango.EllipsizeMode.END)
    return label


class NotificationCard(EventBox):
    """
    One notification: header (app, time, close), image, text, actions.

    Clicking the card runs the notification's "default" action (and closes
    it); without one it calls `on_click`. Action buttons run their action,
    close the notification and call `on_action`.
    """

    def __init__(
        self,
        notification: Notification,
        *,
        show_progress: bool = False,
        show_app: bool = True,
        on_click: Callable[[], None] | None = None,
        on_action: Callable[[], None] | None = None,
        on_hover: Callable[[bool], None] | None = None,
        **kwargs,
    ):
        super().__init__(
            events=["enter-notify", "leave-notify", "button-release"], **kwargs
        )
        self.notification = notification
        self.hovered = False
        self._on_click = on_click
        self._on_action = on_action
        self._on_hover = on_hover

        actions = list(notification.actions)
        self._default_action = next(
            (a for a in actions if a.identifier == DEFAULT_ACTION), None
        )
        buttons = [a for a in actions if a.identifier != DEFAULT_ACTION and a.label]

        self.time_label = Label(name="notification-time", v_align="start")
        self.update_time()
        close_btn = Button(
            name="notification-close-btn",
            image=Image(icon_name="window-close-symbolic", icon_size=12),
            tooltip_text="Dismiss",
            v_align="start",
            on_clicked=lambda *_: notification.close("dismissed-by-user"),
        )

        summary = _wrapping_label(
            _escape(notification.summary or ""), "notification-summary", 2
        )
        summary.set_hexpand(True)
        title_row = Box(spacing=6, children=[summary])
        text_box = Box(
            orientation="v", h_expand=True, v_align="center", children=[title_row]
        )
        if notification.body:
            text_box.add(
                _wrapping_label(body_markup(notification.body), "notification-body", 4)
            )

        content = Box(name="notification-content", spacing=12)
        if pixbuf := notification_image(notification):
            image = RoundedCoverImage(IMAGE_SIZE, IMAGE_SIZE, radius=10)
            image.set_pixbuf(pixbuf)
            image.set_valign(Gtk.Align.START)
            content.add(image)
        content.add(text_box)

        if show_app:
            header = CenterBox(
                name="notification-header",
                start_children=[
                    app_icon(notification, 16),
                    Label(
                        notification.app_name or "Notification",
                        name="notification-app-name",
                        ellipsization="end",
                    ),
                    self.time_label,
                ],
                end_children=[close_btn],
            )
            children: list[Gtk.Widget] = [header, content]
        else:
            # in a list grouped by app the group header names the app, so
            # the time and close button share the summary's line instead
            title_row.add(self.time_label)
            title_row.add(close_btn)
            content.add_style_class("compact")
            children = [content]
        if buttons:
            children.append(
                Box(
                    name="notification-actions",
                    spacing=6,
                    homogeneous=True,
                    children=[self._action_button(a) for a in buttons],
                )
            )

        self.progress_bar = Gtk.ProgressBar(name="notification-progress-bar")
        self.progress_bar.set_fraction(1.0)
        self.progress_bar.set_no_show_all(True)
        self.progress_bar.set_visible(show_progress)
        children.append(self.progress_bar)

        self.box = Box(name="notification-box", orientation="v", children=children)
        if notification.urgency >= URGENCY_CRITICAL:
            self.box.add_style_class("critical")
        if self._default_action is not None or on_click is not None:
            # the hand cursor (utils/cursors.py) looks for this on the EventBox
            self.add_style_class("clickable")
        self.add(self.box)

        self.connect("enter-notify-event", self._on_enter)
        self.connect("leave-notify-event", self._on_leave)
        self.connect("button-release-event", self._on_release)

    def update_time(self):
        self.time_label.set_label(relative_time(self.notification.time))

    def _action_button(self, action: NotificationAction) -> Button:
        return Button(
            label=action.label,
            style_classes=["notification-action"],
            h_expand=True,
            on_clicked=lambda *_: self._run(action),
        )

    def _run(self, action: NotificationAction):
        action.invoke()
        self.notification.close("dismissed-by-user")
        if self._on_action:
            self._on_action()

    def _on_release(self, _, event: Gdk.EventButton):
        if event.button != Gdk.BUTTON_PRIMARY:
            return False
        if self._default_action is not None:
            self._run(self._default_action)
        elif self._on_click is not None:
            self._on_click()
        return True

    def _set_hovered(self, hovered: bool):
        if hovered == self.hovered:
            return
        self.hovered = hovered
        (self.box.add_style_class if hovered else self.box.remove_style_class)(
            "hovered"
        )
        if self._on_hover:
            self._on_hover(hovered)

    def _on_enter(self, *_):
        self._set_hovered(True)

    def _on_leave(self, _, event: Gdk.EventCrossing):
        # moving onto a child (a button) isn't leaving the card
        if event.detail != Gdk.NotifyType.INFERIOR:
            self._set_hovered(False)
