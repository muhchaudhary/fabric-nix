import json
import os

from gi.repository import GLib
from loguru import logger
from thefuzz import fuzz, process
from widgets.popup_window import PopupWindow

from fabric.utils import Application, exec_shell_command_async, get_desktop_applications
from fabric.widgets import Box, Button, Entry, Image, Label, ScrolledWindow

CACHE_DIR = str(GLib.get_user_cache_dir()) + "/fabric"
APP_CACHE = CACHE_DIR + "/app_launcher"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
if not os.path.exists(APP_CACHE):
    os.makedirs(APP_CACHE)


def get_recent_apps() -> list:
    recent_apps_list = []
    if os.path.exists(APP_CACHE + "/last_launched.json"):
        f = open(APP_CACHE + "/last_launched.json", "r")
        try:
            recent_apps_list = json.load(f)
        except json.JSONDecodeError:
            logger.info("[App Menu] Cache file does not exist or is corrupted")
        f.close()
    return recent_apps_list


class ApplicationButton(Button):
    def __init__(self, app: Application, **kwargs):
        self.app: Application = app
        self.app_icon_symbolic = Image(
            icon_name=self.app.icon_name + "-symbolic"
            if self.app.icon_name
            else "application-x-executable-symbolic",
            pixel_size=36,
        )

        self.app_name = Label(
            name="appmenu-app-name",
            label=self.app.display_name,
            justfication="left",
            ellipsization="end",
        )
        self.app_description = (
            Label(
                name="appmenu-app-desc",
                label=self.app.description,
                justfication="left",
                ellipsization="end",
            )
            if self.app.description
            else Label("")
        )
        self.button_box = Box(
            spacing=5,
            children=[
                self.app_icon_symbolic,
                Box(
                    v_align="center",
                    spacing=5,
                    children=[
                        self.app_name,
                        Label("󰧞") if self.app.description else Label(""),
                        self.app_description,
                    ],
                ),
            ],
        )
        super().__init__(name="appmenu-button", **kwargs)
        self.connect("clicked", lambda _: self.launch_app())
        self.connect("focus", lambda *_: self.set_app_icon(self.is_focus()))
        self.add(self.button_box)

    def set_app_icon(self, focus_event):
        app_icon = (
            self.app.icon_name if self.app.icon_name else "application-x-executable"
        )

        self.app_icon_symbolic.set_from_icon_name(
            app_icon if not focus_event else app_icon + "-symbolic", 1
        )

    def launch_app(self):
        command = " ".join(
            [arg for arg in self.app.command_line.split() if "%" not in arg]
        )
        logger.info(f"Attempting to launch {self.app.name} with command {command}")
        exec_shell_command_async(
            f"hyprctl dispatch exec -- {command}",
            lambda *_: logger.info(f"Launched {self.app.name}"),
        ) if command else None

    def add_app_to_json(self) -> list:
        data = get_recent_apps()

        with open(APP_CACHE + "/last_launched.json", "w") as f:
            if self.app.name in data:
                data.remove(self.app.name)
            data.insert(0, self.app.name)
            data.pop() if len(data) > 6 else None
            json.dump(data, f)
            f.close()

        return data


class AppMenu(PopupWindow):
    def __init__(self, **kwargs):
        self.scrolled_window = ScrolledWindow(
            name="appmenu-scroll",
            min_content_height=400,
            visible=False,
        )
        self.applications = sorted(
            get_desktop_applications(),
            key=lambda x: x.name.lower(),
        )
        self.application_buttons = {}
        self.buttons_box = Box(orientation="v")

        # Entry
        self.search_app_entry = Entry(
            name="appmenu-entry",
            placeholder_text="Type to search...",
            editable=True,
        )
        self.search_app_entry.set_icon_from_icon_name(
            0, "preferences-system-search-symbolic"
        )
        self.search_app_entry.connect("key-release-event", self.on_keypress)

        # Application buttons
        for app in self.applications:
            app_button = ApplicationButton(app)
            self.application_buttons[app.name] = app_button
            app_button.connect("clicked", self.on_app_launch)
            self.buttons_box.add(app_button)
        self.app_names = self.application_buttons.keys()
        self.searched_buttons_box = Box(orientation="v", visible=False)
        self.scrolled_window.add_children(
            Box(
                orientation="v",
                children=[
                    self.buttons_box,
                    self.searched_buttons_box,
                ],
            ),
        )

        self.recent_applications = Box(orientation="v")
        self.update_recent_apps()

        super().__init__(
            transition_duration=300,
            anchor="center",
            transition_type="slide-down",
            child=Box(
                name="appmenu",
                orientation="v",
                spacing=20,
                children=[
                    self.search_app_entry,
                    self.recent_applications,
                    self.scrolled_window,
                ],
            ),
            enable_inhibitor=True,
            keyboard_mode="on-demand",
        )
        self.revealer.connect(
            "notify::child-revealed", lambda *args: self.search_app_entry.grab_focus()
        )

    def update_recent_apps(self, recent_apps: list | None = None):
        self.recent_applications.reset_children()
        self.recent_applications.add_children(
            Label(
                name="appmenu-heading",
                label="Recently Used",
                justfication="left",
                h_align="start",
            )
        )
        recent_apps = get_recent_apps() if not recent_apps else recent_apps
        for app_id in recent_apps:
            for app in self.applications:
                if app.name == app_id:
                    recent_app_button = ApplicationButton(app)
                    recent_app_button.connect("clicked", self.on_app_launch)
                    self.recent_applications.add_children(recent_app_button)

    def on_app_launch(self, app_button: ApplicationButton, *_):
        self.toggle_popup()
        self.update_recent_apps(app_button.add_app_to_json())

    def toggle_popup(self):
        self.search_app_entry.set_text("")
        self.reset_app_menu()
        self.scrolled_window.hide()
        self.recent_applications.show()
        super().toggle_popup()

    def on_keypress(self, entry: Entry, event_key):
        if event_key.get_keycode()[1] == 9:
            self.toggle_popup()
        if entry.get_text() == " " or entry.get_text() == "":
            self.reset_app_menu()
            self.scrolled_window.hide()
            self.recent_applications.show()
            return
        self.scrolled_window.show()
        self.recent_applications.hide()
        lister = process.extract(
            entry.get_text(),
            self.app_names,
            scorer=fuzz.partial_ratio,
            limit=10,
        )
        for elem_i in range(len(lister)):
            name = lister[elem_i][0]
            self.buttons_box.reorder_child(self.application_buttons[name], elem_i)

    def reset_app_menu(self):
        i = 0
        for app_button in self.application_buttons.values():
            self.buttons_box.reorder_child(app_button, i)
            i += 1
