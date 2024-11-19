from fabric import Application
from clipboard_history import ClipboardHistory
import gi
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.wayland import WaylandWindow
from fabric.widgets.label import Label
from fabric.widgets.image import Image

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf


class ClipboardHistoryItem(Box):
    def __init__(
        self,
        clipboard_id: str,
        clipboard_client: ClipboardHistory,
    ):
        self.clipboard_client = clipboard_client
        self.clipboard_id = clipboard_id
        self.delete_button = Button(label="Del", on_clicked=self.on_deleted_item)
        self.copy_button = Button(
            label="Copy",
            on_clicked=lambda *_: self.clipboard_client.cliphist_copy(
                self.clipboard_id
            ),
        )
        preview = self.clipboard_client.clipboard_history[clipboard_id]
        self.clipboard_child = Box(
            size=(64, 64),
            children=Label(markup=preview)
            if isinstance(preview, str)
            else Image(pixbuf=preview)
            if isinstance(preview, GdkPixbuf.Pixbuf)
            else Label("You messed up..."),
        )

        super().__init__(
            children=[self.delete_button, self.copy_button, self.clipboard_child]
        )

    def update_clipbaord_child_pixbuf(self, data):
        self.clipboard_child.children = (
            Image(pixbuf=data) if isinstance(data, GdkPixbuf.Pixbuf) else Label(data)
        )

    def on_deleted_item(self, *_):
        self.clipboard_client.cliphist_delete(self.clipboard_id)
        # self.destroy()


class ClipboardHistoryBox(Box):
    def __init__(self):
        self.child_dict = {}
        super().__init__(orientation="v", spacing=10, size=100)
        self.ch_service = ClipboardHistory()
        self.ch_service.connect("notify::clipboard-history", self.on_new_clipboard)
        self.ch_service.connect("clipboard-deleted", self.on_clipboard_delete)
        self.ch_service.connect("clipboard-data-ready", self.on_clipboard_decoded)
        # self.ch_service.connect("clipboard-copied", self.on_clipboard_copied)

    def on_clipboard_decoded(self, _, clipboard_id: str):
        self.child_dict[clipboard_id].update_clipbaord_child_pixbuf(
            self.ch_service.decoded_clipboard_history[clipboard_id]
        )

    def on_clipboard_copied(self, _, clipboard_id: str):
        pass

    def on_clipboard_delete(self, _, clipboard_id: str):
        self.child_dict.pop(clipboard_id).destroy()

    def on_new_clipboard(self, *_):
        self.child_dict.clear()
        for child in self.children:
            child.destroy()
        for key in self.ch_service.clipboard_history.keys():
            item = ClipboardHistoryItem(key, self.ch_service)
            self.child_dict[key] = item
            self.add(item)

        self.ch_service.decode_clipboard()


app = Application()
chb = ClipboardHistoryBox()
WaylandWindow(layer="overlay", anchor="bottom left", child=chb)
app.run()
