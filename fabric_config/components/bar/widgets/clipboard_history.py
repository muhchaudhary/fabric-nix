import os
import re
from collections.abc import Callable

import gi
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.scrolledwindow import ScrolledWindow

from fabric_config import config
from fabric_config.services.clipboard_history import ClipEntry, Pin
from fabric_config.widgets.popup_window_v2 import PopupWindow
from fabric_config.widgets.rounded_cover_image import RoundedCoverImage

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, GLib  # noqa: E402

PANEL_WIDTH = 420
MAX_HISTORY_ROWS = 50
# Image cards show the whole image (never enlarged). Their height follows the
# image's aspect ratio at the card's width, clamped to this range.
CARD_WIDTH = 360  # approximate card width, for sizing before layout
CARD_MIN_HEIGHT = 90
CARD_MAX_HEIGHT = 240
CARD_RADIUS = 10


def _card_height(dimensions: tuple[int, int] | None) -> int:
    if not dimensions or dimensions[0] <= 0:
        return 160
    width, height = dimensions
    fitted = CARD_WIDTH * height / width
    # no taller than the image itself, since it's never enlarged
    return round(max(CARD_MIN_HEIGHT, min(fitted, height, CARD_MAX_HEIGHT)))


THUMB_SIZE = 28  # small thumbnail for image files
CLEAR_CONFIRM_SECONDS = 3

_IMG_SRC_RE = re.compile(r'<img[^>]+src="(?:https?://)?([^/"]+)')


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _describe_entry(entry: ClipEntry) -> tuple[str, str, str | None]:
    """(icon name, label, tooltip) for a history entry."""
    if entry.kind == "image":
        parts = ["Image"]
        if entry.image_format:
            parts.append(entry.image_format.upper())
        if entry.dimensions:
            parts.append(f"{entry.dimensions[0]}×{entry.dimensions[1]}")
        if entry.size_label:
            parts.append(entry.size_label)
        return "image-x-generic-symbolic", " · ".join(parts), None
    if entry.kind == "html":
        m = _IMG_SRC_RE.search(entry.preview)
        return (
            "image-x-generic-symbolic",
            f"Image from {m.group(1)}" if m else "Image (HTML)",
            None,
        )
    if entry.kind == "file" and entry.path:
        return "text-x-generic-symbolic", os.path.basename(entry.path), entry.path
    return "edit-paste-symbolic", _one_line(entry.preview), None


def _describe_pin(pin: Pin) -> tuple[str, str, str | None]:
    if pin.kind == "image":
        return "image-x-generic-symbolic", "Image", None
    text = pin.text or ""
    return "edit-paste-symbolic", _one_line(text)[:200], None


class ClipboardItemRow(Box):
    """
    One entry. Text-like entries are a single line with an icon; image entries
    (card_caption set) are a card: a rounded, cover-cropped preview with a
    caption chip. Image files get a small rounded thumbnail in place of the icon.
    """

    def __init__(
        self,
        icon_name: str,
        label: str,
        tooltip: str | None,
        on_copy: Callable[[], None],
        on_toggle_pin: Callable[[], None],
        on_delete: Callable[[], None] | None,
        pinned: bool,
        card_caption: str | None = None,
        card_dimensions: tuple[int, int] | None = None,
        **kwargs,
    ):
        super().__init__(orientation="v", h_expand=True, **kwargs)
        self._is_card = card_caption is not None

        # separator above the row (hidden for the first row of a list); kept
        # inside the row so in-place reordering doesn't need to move separators
        self.separator = Box(style_classes=["clipboard-separator"])
        self.separator.set_no_show_all(True)

        if self._is_card:
            self._card_sized = card_dimensions is not None
            self._cover = RoundedCoverImage(
                -1, _card_height(card_dimensions), radius=CARD_RADIUS, fit="contain"
            )
            self._cover.set_hexpand(True)
            content = Overlay(
                child=self._cover,
                overlays=Box(
                    name="clipboard-card-caption",
                    h_align="start",
                    v_align="end",
                    children=Label(label=card_caption),
                ),
            )
        else:
            self._icon = Image(
                icon_name=icon_name, icon_size=14, style_classes=["clipboard-item-icon"]
            )
            self._thumb = RoundedCoverImage(THUMB_SIZE, THUMB_SIZE, radius=6)
            self._thumb.set_no_show_all(True)
            self._thumb.hide()
            # max_chars_width=1 + fill: take the row's width and ellipsize,
            # instead of requesting the full text width (which stretched the panel)
            self._label = Label(
                label=label,
                h_align="fill",
                ellipsization="end",
                max_chars_width=1,
                h_expand=True,
                style_classes=["clipboard-item-label"],
            )
            self._label.set_xalign(0)
            content = Box(
                spacing=10,
                v_align="center",
                children=[self._icon, self._thumb, self._label],
            )

        self.main_btn = Button(
            style_classes=["clipboard-item"] + (["card"] if self._is_card else []),
            h_expand=True,
            tooltip_text=tooltip,
            child=content,
            on_clicked=lambda *_: on_copy(),
        )

        actions = Box(orientation="v" if self._is_card else "h", v_align="center")
        self._pin_btn = Button(
            image=Image(icon_name="view-pin-symbolic", icon_size=12),
            style_classes=["clipboard-item-pin"],
            tooltip_text="Unpin" if pinned else "Pin",
            on_clicked=lambda *_: on_toggle_pin(),
        )
        if pinned:
            self._pin_btn.add_style_class("pinned")
        actions.add(self._pin_btn)
        if on_delete is not None:
            actions.add(
                Button(
                    image=Image(icon_name="user-trash-symbolic", icon_size=12),
                    style_classes=["clipboard-item-delete"],
                    tooltip_text="Delete",
                    on_clicked=lambda *_: on_delete(),
                )
            )

        self.add(self.separator)
        self.add(
            Box(name="clipboard-item-box", spacing=2, children=[self.main_btn, actions])
        )

    def set_first(self, first: bool):
        self.separator.set_visible(not first)

    def set_thumbnail(self, pixbuf: GdkPixbuf.Pixbuf):
        if self._is_card:
            if not self._card_sized:
                # e.g. pins: dimensions weren't known up front; use the aspect
                # ratio of the (downscaled) thumbnail
                self._cover.set_size_request(
                    -1, _card_height((pixbuf.get_width(), pixbuf.get_height()))
                )
                self._card_sized = True
            self._cover.set_pixbuf(pixbuf)
        else:
            self._thumb.set_pixbuf(pixbuf)
            self._thumb.show()
            self._icon.hide()


class ClipboardHistoryPanel(Box):
    def __init__(self, **kwargs):
        super().__init__(orientation="v", spacing=8, name="clipboard-panel", **kwargs)
        self.service = config.clipboard_history

        title = Label(label="Clipboard", name="clipboard-panel-title", h_align="start")
        self._clear_btn = Button(
            label="Clear All", name="clipboard-clear-btn", on_clicked=self._on_clear
        )
        self._clear_confirm_id: int | None = None

        self.add(
            CenterBox(
                h_expand=True, start_children=[title], end_children=[self._clear_btn]
            )
        )

        self._pinned_list = Box(orientation="v", spacing=2, h_expand=True)
        self._pinned_section = Box(
            orientation="v",
            spacing=4,
            name="clipboard-pinned-section",
            children=[
                Label(label="Pinned", name="clipboard-section-header", h_align="start"),
                self._pinned_list,
            ],
        )
        self._pinned_section.set_no_show_all(True)
        self._pinned_section.set_visible(False)

        self._list = Box(
            orientation="v", spacing=2, h_expand=True, name="clipboard-list"
        )
        self._empty_label = Label(
            label="Nothing copied yet", name="clipboard-empty", visible=False
        )

        scrolled = ScrolledWindow(
            h_scrollbar_policy="never",
            min_content_size=(-1, 300),
            max_content_size=(-1, 480),
            # don't pass the labels' natural (full-text) width up to the panel
            propagate_width=False,
            child=Box(
                orientation="v",
                spacing=6,
                children=[self._pinned_section, self._list, self._empty_label],
            ),
        )
        # fixed width; long entries ellipsize instead of widening the panel.
        # (GTK3 ignores min-content-width when the h-scrollbar policy is never)
        scrolled.set_size_request(PANEL_WIDTH, -1)
        self.add(scrolled)

        # rows are kept and updated in place: history rows by cliphist id,
        # pinned rows by pin key
        self._history_rows: dict[str, ClipboardItemRow] = {}
        self._pin_rows: dict[str, ClipboardItemRow] = {}
        self._dirty = True

        self.service.connect("notify::entries", self._on_data_changed)
        self.service.connect("pins-changed", self._on_data_changed)
        self.service.connect("thumbnail-ready", self._on_thumbnail_ready)

    def attach_to_popup(self, popup: PopupWindow):
        # sync whenever the popup opens, however it was opened (bar button,
        # keybind, DBus action): rows only update while visible
        popup.reveal_child.revealer.connect(
            "notify::reveal-child",
            lambda revealer, _: (
                self.sync_if_dirty() if revealer.get_reveal_child() else None
            ),
        )

    # ---- syncing ---------------------------------------------------------

    def _on_data_changed(self, *_):
        # the history changes on every copy; only touch widgets while visible
        if ClipboardHistoryPopup.popup_visible:
            self.sync()
        else:
            self._dirty = True

    def sync_if_dirty(self):
        if self._dirty:
            self.sync()

    def sync(self):
        self._dirty = False
        pins = self.service.pins
        self._sync_rows(
            self._pinned_list,
            self._pin_rows,
            [(pin.key, pin) for pin in pins],
            self._make_pin_row,
        )

        visible: list[tuple[str, ClipEntry]] = []
        for entry in self.service.entries:
            if self.service.pin_for_entry(entry.id):
                continue  # already shown in the pinned section
            visible.append((entry.id, entry))
            if len(visible) >= MAX_HISTORY_ROWS:
                break
        self._sync_rows(self._list, self._history_rows, visible, self._make_history_row)

        self._pinned_section.set_visible(bool(pins))
        self._empty_label.set_visible(not pins and not visible)

    def _sync_rows(self, container: Box, rows: dict, wanted: list, factory: Callable):
        wanted_keys = {key for key, _ in wanted}
        for key in [k for k in rows if k not in wanted_keys]:
            rows.pop(key).destroy()
        for index, (key, item) in enumerate(wanted):
            row = rows.get(key)
            if row is None:
                row = rows[key] = factory(item)
                container.add(row)
                row.show_all()
            container.reorder_child(row, index)
            row.set_first(index == 0)

    def _make_history_row(self, entry: ClipEntry) -> ClipboardItemRow:
        icon, label, tooltip = _describe_entry(entry)
        row = ClipboardItemRow(
            icon,
            label,
            tooltip,
            on_copy=lambda: self._copy(lambda done: self.service.copy(entry.id, done)),
            on_toggle_pin=lambda: self.service.pin(entry.id),
            on_delete=lambda: self.service.delete([entry.id]),
            pinned=False,
            # "Image · PNG · 568×379 · 34 KiB" -> caption "PNG · 568×379 · 34 KiB"
            card_caption=label.removeprefix("Image · ")
            if entry.kind == "image"
            else None,
            card_dimensions=entry.dimensions,
        )
        if entry.kind in ("image", "file"):
            self._request_thumbnail(entry.id, row)
        return row

    def _make_pin_row(self, pin: Pin) -> ClipboardItemRow:
        icon, label, tooltip = _describe_pin(pin)
        row = ClipboardItemRow(
            icon,
            label,
            tooltip,
            on_copy=lambda: self._copy(
                lambda done: self.service.copy_pin(pin.key, done)
            ),
            on_toggle_pin=lambda: self.service.unpin(pin.key),
            on_delete=None,
            pinned=True,
            card_caption=(pin.mime or "image/png").split("/")[-1].upper()
            if pin.kind == "image"
            else None,
        )
        if pin.kind == "image":
            self._request_thumbnail(f"pin:{pin.key}", row)
        return row

    def _request_thumbnail(self, key: str, row: ClipboardItemRow):
        pixbuf = self.service.get_thumbnail(key)
        if pixbuf is not None:
            row.set_thumbnail(pixbuf)
        else:
            self.service.request_thumbnail(key)

    def _on_thumbnail_ready(self, _service, key: str):
        row = (
            self._pin_rows.get(key[4:])
            if key.startswith("pin:")
            else self._history_rows.get(key)
        )
        pixbuf = self.service.get_thumbnail(key)
        if row is not None and pixbuf is not None:
            row.set_thumbnail(pixbuf)

    # ---- actions ---------------------------------------------------------

    def _copy(self, do_copy: Callable[[Callable[[bool], None]], None]):
        # close right away for responsiveness; the copy finishes in the background
        if ClipboardHistoryPopup.popup_visible:
            ClipboardHistoryPopup.toggle_popup()
        do_copy(lambda _ok: None)

    def _on_clear(self, *_):
        # first click arms, second click (within a few seconds) clears
        if self._clear_confirm_id is None:
            self._clear_btn.set_label("Clear history?")
            self._clear_btn.add_style_class("confirm")
            self._clear_confirm_id = GLib.timeout_add_seconds(
                CLEAR_CONFIRM_SECONDS, self._reset_clear_button
            )
            return
        GLib.source_remove(self._clear_confirm_id)
        self._reset_clear_button()
        self.service.clear()

    def _reset_clear_button(self):
        self._clear_confirm_id = None
        self._clear_btn.set_label("Clear All")
        self._clear_btn.remove_style_class("confirm")
        return False


_panel = ClipboardHistoryPanel()

ClipboardHistoryPopup = PopupWindow(
    transition_duration=350,
    anchor="top-left",
    transition_type="slide-down",
    child=_panel,
    enable_inhibitor=True,
)
_panel.attach_to_popup(ClipboardHistoryPopup)


class ClipboardHistoryButton(Button):
    def __init__(self, **kwargs):
        super().__init__(
            image=Image(icon_name="edit-paste-symbolic"),
            style_classes=["button-basic", "button-basic-props", "button-border"],
            on_clicked=self._on_click,
            **kwargs,
        )
        ClipboardHistoryPopup.reveal_child.revealer.connect(
            "notify::reveal-child",
            lambda *_: (
                [
                    self.add_style_class("button-basic-active"),
                    self.remove_style_class("button-basic"),
                ]
                if ClipboardHistoryPopup.popup_visible
                else [
                    self.remove_style_class("button-basic-active"),
                    self.add_style_class("button-basic"),
                ]
            ),
        )

    def _on_click(self, *_):
        # the service keeps the history current, so open immediately; the
        # panel syncs any rows that changed while hidden as it opens
        ClipboardHistoryPopup.toggle_popup()
