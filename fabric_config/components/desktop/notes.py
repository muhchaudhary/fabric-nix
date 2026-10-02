"""
Sticky notes on the desktop: add one from the desktop's right-click menu,
drag it by its top strip, type straight into it. Saved per monitor between
restarts.
"""

import json
import os
import uuid
from collections.abc import Callable

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from gi.repository import Gdk, GLib, Gtk
from loguru import logger

NOTES_FILE = os.path.join(GLib.get_user_data_dir(), "fabric", "desktop_notes.json")
NOTE_WIDTH = 240
SAVE_DELAY_MS = 800

# colour dot cycled by clicking it
NOTE_COLORS = ("yellow", "pink", "blue", "green", "purple")


class NotesStore:
    """All notes, every monitor, in one file."""

    def __init__(self):
        self.notes: list[dict] = []
        self._save_id: int | None = None
        try:
            with open(NOTES_FILE) as f:
                data = json.load(f)
            if isinstance(data, list):
                self.notes = [n for n in data if isinstance(n, dict) and "id" in n]
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            logger.warning(f"[Desktop] Ignoring unreadable notes file: {e}")

    def for_monitor(self, monitor: str) -> list[dict]:
        return [n for n in self.notes if n.get("monitor") == monitor]

    def add(self, monitor: str, x: int, y: int) -> dict:
        note = {
            "id": uuid.uuid4().hex,
            "monitor": monitor,
            "x": x,
            "y": y,
            "text": "",
            "color": NOTE_COLORS[len(self.notes) % len(NOTE_COLORS)],
        }
        self.notes.append(note)
        self.save_soon()
        return note

    def remove(self, note_id: str):
        self.notes = [n for n in self.notes if n["id"] != note_id]
        self.save_soon()

    def save_soon(self):
        # typing changes the text on every key; write once it settles
        if self._save_id is not None:
            GLib.source_remove(self._save_id)
        self._save_id = GLib.timeout_add(SAVE_DELAY_MS, self._save)

    def _save(self):
        self._save_id = None
        try:
            os.makedirs(os.path.dirname(NOTES_FILE), exist_ok=True)
            tmp = NOTES_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.notes, f)
            os.replace(tmp, NOTES_FILE)
        except OSError as e:
            logger.warning(f"[Desktop] Couldn't save notes: {e}")
        return False


class NoteWidget(Box):
    def __init__(
        self,
        note: dict,
        store: NotesStore,
        on_move: Callable[["NoteWidget", int, int], None],
        on_delete: Callable[["NoteWidget"], None],
    ):
        self.note = note
        self.store = store
        self._drag_from: tuple[float, float, int, int] | None = None

        self.color_dot = Button(
            name="note-color",
            tooltip_text="Change colour",
            on_clicked=lambda *_: self._cycle_color(),
        )
        handle = EventBox(
            name="note-handle",
            h_expand=True,
            events=["button-press", "button-release", "pointer-motion"],
            tooltip_text="Drag to move",
        )
        handle.connect("button-press-event", self._on_press)
        handle.connect("button-release-event", self._on_release)
        handle.connect("motion-notify-event", self._on_motion)
        delete = Button(
            name="note-delete",
            label="×",
            tooltip_text="Delete note",
            on_clicked=lambda *_: on_delete(self),
        )

        self.text_view = Gtk.TextView()
        self.text_view.set_name("note-text")
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.set_size_request(NOTE_WIDTH, 60)
        buffer = self.text_view.get_buffer()
        buffer.set_text(note.get("text", ""))
        buffer.connect("changed", self._on_text_changed)

        super().__init__(
            name="desktop-note",
            orientation="v",
            children=[
                Box(name="note-bar", children=[self.color_dot, handle, delete]),
                self.text_view,
            ],
        )
        self._on_move = on_move
        self._apply_color()

    def _apply_color(self):
        for color in NOTE_COLORS:
            self.remove_style_class(f"note-{color}")
        self.add_style_class(f"note-{self.note.get('color', NOTE_COLORS[0])}")

    def _cycle_color(self):
        current = self.note.get("color", NOTE_COLORS[0])
        index = NOTE_COLORS.index(current) if current in NOTE_COLORS else -1
        self.note["color"] = NOTE_COLORS[(index + 1) % len(NOTE_COLORS)]
        self._apply_color()
        self.store.save_soon()

    def _on_text_changed(self, buffer: Gtk.TextBuffer):
        start, end = buffer.get_bounds()
        self.note["text"] = buffer.get_text(start, end, False)
        self.store.save_soon()

    def _on_press(self, _widget, event: Gdk.EventButton):
        if event.button != 1:
            return False
        self._drag_from = (event.x_root, event.y_root, self.note["x"], self.note["y"])
        return True

    def _on_motion(self, _widget, event: Gdk.EventMotion):
        if self._drag_from is None:
            return False
        start_x, start_y, note_x, note_y = self._drag_from
        self._on_move(
            self,
            max(0, round(note_x + event.x_root - start_x)),
            max(0, round(note_y + event.y_root - start_y)),
        )
        return True

    def _on_release(self, *_):
        if self._drag_from is not None:
            self._drag_from = None
            self.store.save_soon()
        return False


class NotesLayer(Gtk.Fixed):
    def __init__(self, store: NotesStore, monitor: str):
        super().__init__()
        self.store = store
        self.monitor = monitor
        for note in store.for_monitor(monitor):
            self._add_widget(note)

    def _add_widget(self, note: dict) -> NoteWidget:
        widget = NoteWidget(note, self.store, self._move, self._delete)
        self.put(widget, note["x"], note["y"])
        widget.show_all()
        return widget

    def add_note(self, x: int, y: int):
        widget = self._add_widget(self.store.add(self.monitor, x, y))
        widget.text_view.grab_focus()

    def _move(self, widget: NoteWidget, x: int, y: int):
        widget.note["x"], widget.note["y"] = x, y
        self.move(widget, x, y)

    def _delete(self, widget: NoteWidget):
        self.store.remove(widget.note["id"])
        widget.destroy()
