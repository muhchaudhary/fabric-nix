from collections.abc import Callable

import gi
from fabric.notifications.service import Notification
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow

from fabric_config import config
from fabric_config.widgets.notification_card import NotificationCard, app_icon
from fabric_config.widgets.popup_window_v2 import PopupWindow
from fabric_config.widgets.toggle_pill import ToggleSwitch

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

PANEL_WIDTH = 400
TIME_REFRESH_SECONDS = 30


def _hidden_until_shown(widget):
    # visibility managed by hand: keep a later show_all() from overriding it
    widget.set_no_show_all(True)
    return widget


class NotificationGroup(Box):
    """One app's notifications, newest first. Collapsed, it shows only the newest."""

    def __init__(
        self,
        first: Notification,
        expanded: bool,
        on_clear: Callable[[str], None],
        on_expanded: Callable[[str, bool], None],
    ):
        super().__init__(orientation="v", spacing=6, name="notification-group")
        self.app_name = app_name = first.app_name
        self.expanded = expanded
        self.cards: list[NotificationCard] = []
        self._on_expanded = on_expanded

        self._count = _hidden_until_shown(Label(name="notification-group-count"))
        self._expand_btn = _hidden_until_shown(
            Button(
                name="notification-group-expand",
                on_clicked=lambda *_: self.set_expanded(not self.expanded),
            )
        )
        header = CenterBox(
            name="notification-group-header",
            start_children=[
                app_icon(first, 16),
                Label(
                    app_name or "Notification",
                    name="notification-group-title",
                    ellipsization="end",
                ),
                self._count,
            ],
            end_children=[
                self._expand_btn,
                Button(
                    name="notification-group-clear",
                    image=Image(icon_name="window-close-symbolic", icon_size=12),
                    tooltip_text="Clear",
                    on_clicked=lambda *_: on_clear(app_name),
                ),
            ],
        )
        self._list = Box(orientation="v", spacing=6)
        self.add(header)
        self.add(self._list)
        self.show_all()

    def add_card(self, card: NotificationCard):
        """Add `card` as the newest."""
        self.cards.insert(0, card)
        self._list.add(card)
        self._list.reorder_child(card, 0)
        card.show_all()
        _hidden_until_shown(card)
        self._refresh()

    def remove_card(self, card: NotificationCard):
        self.cards.remove(card)
        card.destroy()
        self._refresh()

    def set_expanded(self, expanded: bool):
        self.expanded = expanded
        self._on_expanded(self.app_name, expanded)
        self._refresh()

    def _refresh(self):
        count = len(self.cards)
        for index, card in enumerate(self.cards):
            card.set_visible(self.expanded or index == 0)
        self._count.set_label(str(count))
        self._count.set_visible(count > 1)
        self._expand_btn.set_label(
            "Show less" if self.expanded else f"{count - 1} more"
        )
        self._expand_btn.set_visible(count > 1)


class NotificationCenterPanel(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="v", spacing=10, name="notification-center", **kwargs
        )
        self.service = config.notifications
        self._groups: dict[str, NotificationGroup] = {}
        self._cards: dict[int, NotificationCard] = {}
        self._expanded: set[str] = set()
        self._time_source: int | None = None
        self._popup: PopupWindow | None = None

        self._clear_btn = Button(
            label="Clear All",
            name="notification-clear-btn",
            on_clicked=lambda *_: self.service.clear(),
        )
        self.add(
            CenterBox(
                h_expand=True,
                start_children=[
                    Label(label="Notifications", name="notification-center-title")
                ],
                end_children=[self._clear_btn],
            )
        )

        self._dnd_switch = ToggleSwitch(
            active=self.service.dnd,
            on_toggled=self._set_dnd,
            valign=Gtk.Align.CENTER,
        )
        self.add(
            Box(
                name="notification-dnd-row",
                spacing=10,
                children=[
                    Image(icon_name="notification-disabled-symbolic", icon_size=16),
                    Label(label="Do Not Disturb", h_expand=True, h_align="start"),
                    self._dnd_switch,
                ],
            )
        )

        self._list = Box(orientation="v", spacing=12)
        self._empty = _hidden_until_shown(
            Box(
                orientation="v",
                spacing=8,
                name="notification-empty",
                children=[
                    Image(icon_name="notification-symbolic", icon_size=32),
                    Label(label="No notifications"),
                ],
            )
        )
        scrolled = ScrolledWindow(
            h_scrollbar_policy="never",
            max_content_size=(-1, 560),
            # don't pass the labels' natural (full-text) width up to the panel
            propagate_width=False,
            child=Box(orientation="v", children=[self._list, self._empty]),
        )
        # (GTK3 ignores min-content-width when the h-scrollbar policy is never)
        scrolled.set_size_request(PANEL_WIDTH, -1)
        self.add(scrolled)

        # oldest first, so the newest ends up on top
        for notification in reversed(self.service.entries):
            self._add(notification)
        self._update_empty()

        self.service.connect("notification-added", lambda _, n: self._add(n))
        self.service.connect("notification-replaced", self._on_replaced)
        self.service.connect("notification-removed", lambda _, i: self._remove(i))
        self.service.connect(
            "notify::dnd", lambda *_: self._dnd_switch.set_active(self.service.dnd)
        )

    def attach_to_popup(self, popup: PopupWindow):
        self._popup = popup
        popup.reveal_child.revealer.connect(
            "notify::reveal-child",
            lambda revealer, _: self._on_shown(revealer.get_reveal_child()),
        )

    # ---- rows ------------------------------------------------------------

    def _add(self, notification: Notification):
        card = NotificationCard(
            notification, show_app=False, on_action=self._close_popup
        )
        app = notification.app_name
        group = self._groups.get(app)
        if group is None:
            group = self._groups[app] = NotificationGroup(
                notification,
                app in self._expanded,
                on_clear=self.service.clear,
                on_expanded=self._on_expanded,
            )
            self._list.add(group)
        self._list.reorder_child(group, 0)
        group.add_card(card)
        self._cards[notification.id] = card
        self._update_empty()

    def _remove(self, notification_id: int):
        card = self._cards.pop(notification_id, None)
        if card is None:
            return
        group = self._groups[card.notification.app_name]
        group.remove_card(card)
        if not group.cards:
            del self._groups[group.app_name]
            group.destroy()
        self._update_empty()

    def _on_replaced(self, _, old_id: int, notification: Notification):
        # add first, so a group with just the old one isn't torn down and rebuilt
        self._add(notification)
        self._remove(old_id)

    def _on_expanded(self, app_name: str, expanded: bool):
        (self._expanded.add if expanded else self._expanded.discard)(app_name)

    def _update_empty(self):
        empty = not self._cards
        self._empty.set_visible(empty)
        self._clear_btn.set_sensitive(not empty)

    # ---- state -----------------------------------------------------------

    def _set_dnd(self, active: bool):
        if self.service.dnd != active:
            self.service.dnd = active

    def _close_popup(self):
        if self._popup is not None and self._popup.popup_visible:
            self._popup.toggle_popup()

    def _on_shown(self, shown: bool):
        if self._time_source is not None:
            GLib.source_remove(self._time_source)
            self._time_source = None
        if shown:
            self._update_times()
            self._time_source = GLib.timeout_add_seconds(
                TIME_REFRESH_SECONDS, self._update_times
            )

    def _update_times(self):
        for card in self._cards.values():
            card.update_time()
        return True


_panel = NotificationCenterPanel()

NotificationCenterPopup = PopupWindow(
    transition_duration=350,
    anchor="top-right",
    transition_type="slide-down",
    child=_panel,
    enable_inhibitor=True,
)
_panel.attach_to_popup(NotificationCenterPopup)


class NotificationCenterButton(Button):
    def __init__(self, **kwargs):
        self._icon = Image(icon_name="notification-symbolic")
        self._count = _hidden_until_shown(Label(name="notification-count"))
        super().__init__(
            child=Box(spacing=4, children=[self._icon, self._count]),
            style_classes=["button-basic", "button-basic-props", "button-border"],
            tooltip_text="Notifications",
            on_clicked=lambda *_: NotificationCenterPopup.toggle_popup(),
            **kwargs,
        )
        config.notifications.connect("notify::count", self._update)
        config.notifications.connect("notify::dnd", self._update)
        self._update()

        NotificationCenterPopup.reveal_child.revealer.connect(
            "notify::reveal-child",
            lambda *_: (
                [
                    self.add_style_class("button-basic-active"),
                    self.remove_style_class("button-basic"),
                ]
                if NotificationCenterPopup.popup_visible
                else [
                    self.remove_style_class("button-basic-active"),
                    self.add_style_class("button-basic"),
                ]
            ),
        )

    def _update(self, *_):
        service = config.notifications
        icon = "notification-disabled" if service.dnd else "notification"
        if service.count:
            icon += "-new"
        self._icon.set_from_icon_name(f"{icon}-symbolic")
        self._count.set_label(str(service.count))
        self._count.set_visible(service.count > 0)
