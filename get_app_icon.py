from fabric.hyprland.service import Connection
import json
from gi.repository import Gio
import fabric
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.widgets.button import Button
from fabric.widgets.wayland import Window


connection = Connection()

clients = json.loads(
    str(
        connection.send_command(
            "j/clients",
        ).reply.decode()
    )
)

overrides = {"code-insiders-url-handler": "vscode-insiders", "": "show-desktop"}
# icons_boxes = []
# for client in clients:
#     # This does not work for every app, apps like vscode dont set initial class propperly
#     #  Fix this with overrides
#     app_name = client["initialClass"]
#     icons_boxes.append(Image(icon_name=overrides.get(app_name, app_name), icon_size=6))


class IconWindow(Window):
    def __init__(self, **kwargs):
        super().__init__(
            layer="top",
            anchor="bottom right",
            margin="0px 0px 0px 0px",
            all_visible=True,
            exclusive=True,
        )
        self.widgets_container = Box(
            spacing=2,
            orientation="v",
            name="widgets-container",
        )

        connection.connect(signal_spec="activewindow", callback=self.on_active_window)
        self.active_image = Image()
        self.active_label = Label()
        self.widgets_container.add(
            Box(
                orientation="horizontal",
                children=[self.active_image, self.active_label],
            )
        )
        # self.widgets_container.add_children(icons_boxes)
        self.add(self.widgets_container)
        self.show_all()

    def on_active_window(self, a, b):
        app_name = b.data[0]
        app_label = b.data[1]
        self.active_image.set_from_icon_name(overrides.get(app_name, app_name), 6)
        self.active_label.set_label(app_label)


window = IconWindow()
fabric.start()
