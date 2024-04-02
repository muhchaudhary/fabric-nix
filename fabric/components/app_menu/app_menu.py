import gi
from fabric.utils.applications import Application, get_desktop_applications
from fabric.widgets.scrolled_window import ScrolledWindow
from widgets.popup_window import PopupWindow
from fabric.widgets.wayland import Window
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.box import Box

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GObject


class AppInfo(Button):
    def __init__(self, app: Application, **kwargs):
        self.app: Application = app
        self.ctx: Gio.AppLaunchContext = Gio.AppLaunchContext()
        self.app_icon = Image(pixbuf=self.app.get_icon_pixbuf())
        self.actions_list = self.app._app.list_actions()
        self.app_name = Box(
            children=[
                Label(
                    label=self.app.display_name,
                    justfication="left",
                    ellipsization="end",
                ),
            ]
        )
        self.app_description = Box(
            children=Label(
                label=self.app.description,
                justfication="left",
                ellipsization="end",
            )
        )
        self.button_box = Box(
            children=[
                self.app_icon,
                Box(
                    orientation="v",
                    children=[
                        self.app_name,
                        self.app_description,
                        Label(" ".join(self.actions_list)),
                    ],
                ),
            ],
        )
        super().__init__(**kwargs)
        self.connect("clicked", lambda *args: self.launch_app())

        self.add(self.button_box)

    def launch_app(self):
        self.app._app.launch(context=self.ctx)

    def launch_app_action(self, action: str):
        self.app._app.launch_action(action_name=action)


class AppMenu(ScrolledWindow):
    def __init__(self, **kwargs):
        super().__init__(
            name="quicksettings",
            min_content_width=500,
            min_content_height=800,
            **kwargs,
        )
        self.applications = get_desktop_applications()
        self.application_buttons = []
        self.buttons_box = Box(
            orientation="v",
        )
        self.add_children(self.buttons_box)
        for app in self.applications:
            appL = AppInfo(app)
            self.application_buttons.append(appL)
            self.buttons_box.add_children(appL)
            appL.ctx.connect("launched", lambda *args: self.toggle_popup())


apps = AppMenu()


appMenu = PopupWindow(
    transition_duration=300,
    anchor="center",
    transition_type="slide-down",
    child=apps,
    enable_inhibitor=True,
)
