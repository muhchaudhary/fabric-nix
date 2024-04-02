import subprocess
from fabric.utils.applications import Application, get_desktop_applications
from fabric.widgets.entry import Entry
from fabric.widgets.scrolled_window import ScrolledWindow
from widgets.popup_window import PopupWindow
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from thefuzz import process, fuzz


class AppInfo(Button):
    def __init__(self, app: Application, **kwargs):
        self.app: Application = app
        self.app_icon = (
            Image(pixbuf=self.app.get_icon_pixbuf())
            if self.app.get_icon_pixbuf()
            else Image(icon_name="application-x-executable", pixel_size=48)
        )
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
            spacing=5,
            children=[
                self.app_icon,
                Box(
                    orientation="v",
                    children=[
                        self.app_name,
                        self.app_description,
                    ],
                ),
            ],
        )
        super().__init__(name="panel-button", **kwargs)
        self.connect("clicked", lambda *args: self.launch_app())
        self.add(self.button_box)

    def launch_app(self):
        subprocess.Popen(
            [x for x in self.app.command_line.split(" ") if x != "%U"],
            start_new_session=True,
        )

    def launch_app_action(self, action: str):
        subprocess.Popen(
            self.app.command_line.split(" ") + action.split(" "), start_new_session=True
        )


class AppMenu(PopupWindow):
    def __init__(self, **kwargs):
        self.scrolled_window = ScrolledWindow(
            name="quicksettings",
            min_content_width=600,
            min_content_height=400,
        )
        self.applications = sorted(
            get_desktop_applications(), key=lambda x: x.name.lower()
        )
        self.application_buttons = {}
        self.buttons_box = Box(
            orientation="v",
        )
        self.search_app_entry = Entry(
            placeholder_text="Search for an App",
            editable=True,
            style="font-size: 30px;",
        )
        self.search_app_entry.connect("key-release-event", self.keypress)
        for app in self.applications:
            appL = AppInfo(app)
            self.application_buttons[app.name] = app
            self.buttons_box.add_children(appL)
            appL.connect("clicked", lambda *args: appMenu.toggle_popup())
        self.app_names = self.application_buttons.keys()
        self.searched_buttons_box = Box(orientation="v", visible=False)
        self.scrolled_window.add_children(
            Box(
                orientation="v",
                children=[
                    self.search_app_entry,
                    self.buttons_box,
                    self.searched_buttons_box,
                ],
            )
        )
        super().__init__(
            transition_duration=300,
            anchor="center",
            transition_type="slide-down",
            child=self.scrolled_window,
            enable_inhibitor=True,
            keyboard_mode="on-demand",
        )
        self.revealer.connect(
            "notify::child-revealed",
            lambda *args: self.search_app_entry.grab_focus_without_selecting()
            if args[0].get_child_revealed()
            else None,
        )
        # GLib.idle_add(lambda *args: self.search_app_entry.grab_focus_without_selecting())

    def keypress(self, entry: Entry, event_key):
        if event_key.get_keycode()[1] == 9:
            self.on_inhibit_click()
        if entry.get_text() == " " or entry.get_text() == "":
            self.buttons_box.set_visible(True)
            return
        self.buttons_box.set_visible(False)
        self.searched_buttons_box.set_visible(True)
        self.searched_buttons_box.reset_children()
        lister = process.extract(
            entry.get_text(), self.app_names, scorer=fuzz.partial_ratio, limit=10
        )
        for elem in lister:
            name = elem[0]
            appL = AppInfo(self.application_buttons[name])
            self.searched_buttons_box.add_children(appL)
            appL.connect("clicked", lambda *args: appMenu.toggle_popup())
        print(lister)
        print(entry.get_text())


appMenu = AppMenu()
