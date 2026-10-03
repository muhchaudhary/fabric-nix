import json
import os

from fabric.core.service import Property, Service, Signal
from fabric.notifications.service import Notification, Notifications
from gi.repository import GLib
from loguru import logger

HISTORY_PATH = os.path.join(GLib.get_user_cache_dir(), "fabric", "notifications.json")
MAX_ENTRIES = 100
SAVE_DELAY_SECONDS = 2
URGENCY_CRITICAL = 2


def hint(notification: Notification, key: str):
    """A hint of a live notification (restored ones have none)."""
    if getattr(notification, "_hints", None) is None:
        return None
    try:
        return notification.do_get_hint_entry(key)
    except Exception:
        return None


class NotificationCenter(Service):
    """
    The notification server plus a history of what it received.

    A popup timing out doesn't close its notification: it stays live in the
    server (and here), so its actions still work from the notification
    center. Only dismissing it (or the app closing it) removes it.

    The history is saved to disk; entries restored at startup have no actions
    (whoever sent them is gone) and negative ids, so they never collide with
    the server's.
    """

    @Signal
    def notification_added(self, notification: object) -> None: ...

    # `notification` replaces the one with `old_id` (same place, new content)
    @Signal
    def notification_replaced(self, old_id: int, notification: object) -> None: ...

    @Signal
    def notification_removed(self, notification_id: int) -> None: ...

    @Property(bool, "read-write", default_value=False)
    def dnd(self) -> bool:
        return self._dnd

    @dnd.setter
    def dnd(self, value: bool):
        if value != self._dnd:
            self._dnd = value
            self._queue_save()

    @Property(int, "readable")
    def count(self) -> int:
        return len(self._entries)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._dnd = False
        # id -> notification, oldest first
        self._entries: dict[int, Notification] = {}
        # serialized once per entry: serializing re-encodes images as PNG
        self._serialized: dict[int, dict] = {}
        # server removals we caused ourselves (replacements), not to re-announce
        self._silent_removals: set[int] = set()
        self._save_source: int | None = None

        self._load()

        self._server = Notifications()
        self._server.connect("notification-added", self._on_server_added)
        self._server.connect("notification-removed", self._on_server_removed)

    @property
    def entries(self) -> list[Notification]:
        """All notifications, newest first."""
        return list(reversed(self._entries.values()))

    def dismiss(self, notification: Notification):
        notification.close("dismissed-by-user")

    def clear(self, app_name: str | None = None):
        for notification in list(self._entries.values()):
            if app_name is None or notification.app_name == app_name:
                notification.close("dismissed-by-user")

    def should_popup(self, notification: Notification) -> bool:
        return not self._dnd or notification.urgency >= URGENCY_CRITICAL

    # ---- server ----------------------------------------------------------

    def _on_server_added(self, server: Notifications, notification_id: int):
        notification = server.get_notification_from_id(notification_id)
        if notification is None:
            return

        old = self._entries.get(notification.replaces_id)
        if notification.replaces_id and old is not None:
            # drop the old one quietly: closing it would tell its sender it's
            # gone (and end a `notify-send --wait`)
            self._forget(old.id)
            self._silent_removals.add(old.id)
            server.remove_notification(old.id)
            self._remember(notification)
            self.notification_replaced(old.id, notification)
        else:
            self._remember(notification)
            self.notification_added(notification)
        self._trim()

    def _on_server_removed(self, _server, notification_id: int):
        if notification_id in self._silent_removals:
            self._silent_removals.discard(notification_id)
            return
        self._remove(notification_id)

    # ---- entries ---------------------------------------------------------

    def _remember(self, notification: Notification):
        self._entries[notification.id] = notification
        self.notify("count")
        self._queue_save()

    def _forget(self, notification_id: int) -> bool:
        if self._entries.pop(notification_id, None) is None:
            return False
        self._serialized.pop(notification_id, None)
        self.notify("count")
        self._queue_save()
        return True

    def _remove(self, notification_id: int):
        if self._forget(notification_id):
            self.notification_removed(notification_id)

    def _trim(self):
        excess = len(self._entries) - MAX_ENTRIES
        for oldest in list(self._entries.values())[: max(excess, 0)]:
            if oldest.id < 0:
                self._remove(oldest.id)
            else:
                oldest.close("expired")

    # ---- persistence -----------------------------------------------------

    def _load(self):
        try:
            with open(HISTORY_PATH) as f:
                data = json.load(f)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as e:
            logger.warning(f"[Notifications] Couldn't read the history: {e}")
            return

        self._dnd = bool(data.get("dnd", False))
        saved = data.get("notifications", [])
        for index, item in enumerate(saved):
            # their senders are gone, so actions would go nowhere
            item = {**item, "id": -(len(saved) - index), "actions": []}
            try:
                notification = Notification.deserialize(item)  # type: ignore
            except Exception as e:
                logger.warning(f"[Notifications] Skipping a saved notification: {e}")
                continue
            # no server behind these: closing one just removes it
            notification.connect("closed", lambda n, _reason: self._remove(n.id))
            self._entries[notification.id] = notification
            self._serialized[notification.id] = item

    def _queue_save(self):
        if self._save_source is None:
            self._save_source = GLib.timeout_add_seconds(SAVE_DELAY_SECONDS, self._save)

    def _save(self):
        self._save_source = None
        items = []
        for notification in self._entries.values():
            item = self._serialized.get(notification.id)
            if item is None:
                try:
                    item = notification.serialize()
                except Exception as e:
                    logger.warning(
                        f"[Notifications] Can't save notification {notification.id}: {e}"
                    )
                    continue
                self._serialized[notification.id] = item  # type: ignore
            items.append(item)

        tmp_path = HISTORY_PATH + ".tmp"
        try:
            os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
            with open(tmp_path, "w") as f:
                json.dump({"dnd": self._dnd, "notifications": items}, f)
            os.replace(tmp_path, HISTORY_PATH)
        except OSError as e:
            logger.error(f"[Notifications] Couldn't save the history: {e}")
        return False
