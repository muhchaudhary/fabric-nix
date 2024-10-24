import json
import os

from gi.repository import GLib
from loguru import logger
from thefuzz import fuzz, process
from widgets.popup_window_v2 import PopupWindow

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow

from fabric.utils.helpers import (
    DesktopApp,
    get_desktop_applications,
    exec_shell_command_async,
)

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
    def __init__(self, app: DesktopApp, **kwargs):
        self.app: DesktopApp = app
        self.app_icon_symbolic = Image(
            icon_name=self.app.icon_name
            if self.app.icon_name and ".png" not in self.app.icon_name
            else "application-x-executable-symbolic",
            icon_size=36,  # does not do anything
        )
        self.app_icon_symbolic.set_pixel_size(36)

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
        super().__init__(
            name="appmenu-button",
            **kwargs,
        )
        self.add(self.button_box)

    def launch_app(self):
        command = (
            " ".join([arg for arg in self.app.command_line.split() if "%" not in arg])
            if self.app.command_line
            else None
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
            max_content_size=(-1, 437),
            min_content_size=(-1, 437),
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
            placeholder="Type to search...",
            editable=True,
            on_changed=self.on_entry_change,
        )
        self.search_app_entry.set_icon_from_icon_name(
            0, "preferences-system-search-symbolic"
        )

        # Application buttons
        for app in self.applications:
            app_button = ApplicationButton(app, on_clicked=self.on_app_launch)
            self.application_buttons[app.name] = app_button
            self.buttons_box.add(app_button)
        self.scrolled_window.children = (
            Box(orientation="v", children=self.buttons_box),
        )

        # Recent applications
        self.recent_applications = Box(orientation="v")
        self.update_recent_apps()

        super().__init__(
            transition_duration=300,
            anchor="center",
            transition_type="slide-down",
            child=Box(
                size=(700, 450),
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
            "notify::child-revealed", lambda *_: self.search_app_entry.grab_focus()
        )

    def update_recent_apps(self, recent_apps: list | None = None):
        self.recent_applications.children = []
        self.recent_applications.children = Label(
            name="appmenu-heading",
            label="Recently Used",
            justfication="left",
            h_align="start",
        )
        recent_apps = get_recent_apps() if not recent_apps else recent_apps
        for app_id in recent_apps:
            for app in self.applications:
                if app.name == app_id:
                    recent_app_button = ApplicationButton(
                        app, on_clicked=self.on_app_launch
                    )
                    self.recent_applications.children = (
                        self.recent_applications.children + [recent_app_button]
                    )

    def on_app_launch(self, app_button: ApplicationButton, *_):
        app_button.launch_app()
        self.toggle_popup()
        self.update_recent_apps(app_button.add_app_to_json())

    def toggle_popup(self, monitor: int | None = None):
        self.search_app_entry.set_text("")
        self.reset_app_menu()
        self.scrolled_window.hide()
        self.recent_applications.show()
        super().toggle_popup(monitor=True)

    def on_entry_change(self, entry: Entry):
        if entry.get_text() == " " or entry.get_text() == "":
            self.reset_app_menu()
            self.scrolled_window.hide()
            self.recent_applications.show()
            return
        self.scrolled_window.show()
        self.recent_applications.hide()
        lister = process.extract(
            entry.get_text(),
            self.application_buttons.keys(),
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
