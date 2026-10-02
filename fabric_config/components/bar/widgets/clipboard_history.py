import json
import os
import re
from collections.abc import Callable

import gi
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow

from fabric_config import config
from fabric_config.widgets.popup_window_v2 import PopupWindow

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, GLib  # noqa: E402

_BINARY_RE = re.compile(r"\[\[ binary data .* \]\]")

_CACHE_DIR = os.path.join(GLib.get_user_cache_dir(), "fabric", "clipboard")
_PINNED_CACHE_FILE = os.path.join(_CACHE_DIR, "pinned.json")
os.makedirs(_CACHE_DIR, exist_ok=True)


def _load_pinned_ids() -> set[str]:
    try:
        with open(_PINNED_CACHE_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_pinned_ids(pinned: set[str]) -> None:
    try:
        with open(_PINNED_CACHE_FILE, "w") as f:
            json.dump(list(pinned), f)
    except Exception:
        pass


_pinned_ids: set[str] = _load_pinned_ids()


def _scale_pixbuf(
    pixbuf: GdkPixbuf.Pixbuf, max_width: int, max_height: int
) -> GdkPixbuf.Pixbuf:
    w, h = pixbuf.get_width(), pixbuf.get_height()
    if w == 0 or h == 0:
        return pixbuf
    scale = min(max_width / w, max_height / h, 1.0)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    return pixbuf.scale_simple(nw, nh, GdkPixbuf.InterpType.BILINEAR)


class ClipboardItemRow(Box):
    def __init__(
        self,
        cliphist_id: str,
        on_pin_changed: Callable | None = None,
        **kwargs,
    ):
        super().__init__(h_expand=True, spacing=0, name="clipboard-item-box", **kwargs)
        self.cliphist_id = cliphist_id
        self._is_pinned = cliphist_id in _pinned_ids
        self._on_pin_changed = on_pin_changed

        preview = config.clipboard_history.clipboard_history.get(cliphist_id, "")
        is_media = bool(_BINARY_RE.match(preview) or preview.startswith("<meta"))

        self._icon = Image(
            icon_name="image-x-generic-symbolic" if is_media else "edit-paste-symbolic",
            icon_size=14,
            style_classes=["clipboard-item-icon"],
        )
        self._label = Label(
            label="[Image]" if is_media else preview[:120].replace("\n", " "),
            h_align="start",
            ellipsize="end",
            style_classes=["clipboard-item-label"],
            h_expand=True,
        )
        self._thumbnail = Image(
            style_classes=["clipboard-item-thumbnail"], visible=False
        )

        self.main_btn = Button(
            style_classes=["clipboard-item"],
            h_expand=True,
            child=Box(
                spacing=8,
                v_align="center",
                children=[self._icon, self._thumbnail, self._label],
            ),
        )
        self.main_btn.connect("clicked", self._on_copy)

        self._pin_btn = Button(
            image=Image(icon_name="view-pin-symbolic", icon_size=12),
            style_classes=["clipboard-item-pin"],
            tooltip_text="Pin",
        )
        if self._is_pinned:
            self._pin_btn.add_style_class("pinned")
        self._pin_btn.connect("clicked", self._on_pin)

        self._delete_btn = Button(
            image=Image(icon_name="user-trash-symbolic", icon_size=12),
            style_classes=["clipboard-item-delete"],
            tooltip_text="Delete",
        )
        self._delete_btn.set_sensitive(not self._is_pinned)
        self._delete_btn.connect("clicked", self._on_delete)

        self.add(self.main_btn)
        self.add(self._pin_btn)
        self.add(self._delete_btn)

        self._signal_id: int | None = config.clipboard_history.connect(
            "clipboard-data-ready", self._on_data_ready
        )
        self.connect("destroy", self._on_destroy)
        config.clipboard_history.decode_item(cliphist_id)

    def _on_data_ready(self, _service, ready_id: str):
        if ready_id != self.cliphist_id:
            return
        decoded = config.clipboard_history.decoded_clipboard_history.get(
            self.cliphist_id
        )
        if isinstance(decoded, GdkPixbuf.Pixbuf):
            self._thumbnail.set_from_pixbuf(_scale_pixbuf(decoded, 160, 112))
            self._thumbnail.set_visible(True)
            self._icon.set_visible(False)
            self._label.set_visible(False)
        elif isinstance(decoded, str) and decoded:
            self._label.set_label(decoded[:120].replace("\n", " "))

    def _on_copy(self, _):
        config.clipboard_history.cliphist_copy(self.cliphist_id)

    def _on_pin(self, _):
        self._is_pinned = not self._is_pinned
        if self._is_pinned:
            _pinned_ids.add(self.cliphist_id)
        else:
            _pinned_ids.discard(self.cliphist_id)
        _save_pinned_ids(_pinned_ids)
        if self._on_pin_changed:
            self._on_pin_changed()

    def _on_delete(self, _):
        config.clipboard_history.cliphist_delete(
            self.cliphist_id, on_done=config.clipboard_history.cliphist_list
        )

    def _on_destroy(self, _):
        if self._signal_id is not None:
            try:
                config.clipboard_history.disconnect(self._signal_id)
            except Exception:
                pass
            self._signal_id = None


class ClipboardHistoryPanel(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="v",
            spacing=8,
            name="clipboard-panel",
            **kwargs,
        )

        title = Label(label="Clipboard", name="clipboard-panel-title", h_align="start")
        clear_btn = Button(label="Clear All", name="clipboard-clear-btn")
        clear_btn.connect("clicked", self._on_clear_all)

        self.add(
            CenterBox(
                h_expand=True,
                start_children=[title],
                end_children=[clear_btn],
            )
        )

        self._pinned_list = Box(orientation="v", spacing=2, h_expand=True)
        self._pinned_section = Box(
            orientation="v",
            spacing=4,
            name="clipboard-pinned-section",
            visible=False,
            children=[
                Label(
                    label="Pinned",
                    name="clipboard-section-header",
                    h_align="start",
                ),
                self._pinned_list,
            ],
        )

        self._list = Box(
            orientation="v", spacing=2, h_expand=True, name="clipboard-list"
        )

        self.add(
            ScrolledWindow(
                min_content_size=(-1, 300),
                max_content_size=(-1, 480),
                h_expand=True,
                child=Box(
                    orientation="v",
                    spacing=6,
                    children=[self._pinned_section, self._list],
                ),
            )
        )

        self._on_refresh_done: Callable | None = None

        config.clipboard_history.connect(
            "notify::clipboard-history", self._on_history_changed
        )

    def refresh(self, on_done=None):
        self._on_refresh_done = on_done
        config.clipboard_history.cliphist_list()

    def _on_history_changed(self, *_):
        # The history changes on every copy. Only rebuild while the popup is
        # open or about to open: each row decodes its item, which may spawn a
        # `cliphist decode` process. Opening the popup always refreshes.
        if not ClipboardHistoryPopup.popup_visible and not self._on_refresh_done:
            return
        self._rebuild_sections()
        if self._on_refresh_done:
            cb, self._on_refresh_done = self._on_refresh_done, None
            cb()

    def _rebuild_sections(self):
        for child in self._pinned_list.get_children():
            child.destroy()
        for child in self._list.get_children():
            child.destroy()

        has_pinned = False
        unpinned_shown = 0
        for cliphist_id in config.clipboard_history.clipboard_history:
            # pinned items are always shown; the rest are capped at 50
            is_pinned = cliphist_id in _pinned_ids
            if not is_pinned:
                if unpinned_shown >= 50:
                    continue
                unpinned_shown += 1
            row = ClipboardItemRow(cliphist_id, on_pin_changed=self._rebuild_sections)
            if is_pinned:
                self._pinned_list.add(row)
                has_pinned = True
            else:
                self._list.add(row)

        self._pinned_section.set_visible(has_pinned)

    def _on_clear_all(self, _):
        config.clipboard_history.cliphist_delete(
            [
                cliphist_id
                for cliphist_id in config.clipboard_history.clipboard_history
                if cliphist_id not in _pinned_ids
            ],
            on_done=config.clipboard_history.cliphist_list,
        )


_panel = ClipboardHistoryPanel()

ClipboardHistoryPopup = PopupWindow(
    transition_duration=350,
    anchor="top-left",
    transition_type="slide-down",
    child=_panel,
    enable_inhibitor=True,
)


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
        if ClipboardHistoryPopup.popup_visible:
            ClipboardHistoryPopup.toggle_popup()
        else:
            _panel.refresh(on_done=ClipboardHistoryPopup.toggle_popup)
