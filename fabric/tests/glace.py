import gi

from fabric.widgets.box import Box
from fabric.widgets.image import Image
from fabric.widgets.button import Button

from utils.icon_resolver import IconResolver

gi.require_version("Glace", "0.1")
from gi.repository import Glace
class OpenAppsBar(Box):
    def __init__(self):
        super().__init__(spacing=10)
        self.icon_resolver = IconResolver()
        self._manager = Glace.Manager()
        self._manager.connect("client-added", self.on_client_added)

    def on_client_added(self, _, client: Glace.Client):
        client_image = Image()
        client_button = Button(
            name="panel-button",
            image=client_image,
        )
        client.connect(
            "notify::app-id",
            lambda *_: client_image.set_from_pixbuf(
                self.icon_resolver.get_icon_pixbuf(client.get_app_id(), 16)
            ),
        )
        client.bind_property("title", client_button, "tooltip-text", 0)
        client_button.connect("button-press-event", lambda *_: client.activate())

        self.add(client_button)

        client.connect("close", lambda *_: self.remove(client_button))
