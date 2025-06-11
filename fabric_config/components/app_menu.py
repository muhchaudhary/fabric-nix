import json
import os
from fabric.utils import (
    DesktopApp,
    exec_shell_command_async,
    get_desktop_applications,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.shapes import Corner
from gi.repository import GLib
from loguru import logger
from thefuzz import fuzz, process

from fabric_config.widgets.popup_window_v2 import PopupWindow

CACHE_DIR = str(GLib.get_user_cache_dir()) + "/fabric"
APP_CACHE = CACHE_DIR + "/app_launcher"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
if not os.path.exists(APP_CACHE):
    os.makedirs(APP_CACHE)


def get_recent_apps() -> list:
    recent_apps_list = []
    if os.path.exists(APP_CACHE + "/last_launched.json"):
        with open(APP_CACHE + "/last_launched.json", "r") as f:
            try:
                recent_apps_list = json.load(f)
            except json.JSONDecodeError:
                logger.info("[App Menu] Cache file does not exist or is corrupted")
            finally:
                f.close()
    return recent_apps_list


class ApplicationButtonV2(Button):
    def __init__(self, app_info: DesktopApp, **kwargs):
        self.app_info = app_info
        super().__init__(
            name="appmenu-button",
            h_expand=True,
            v_expand=True,
            style_classes=["cool-border"],
            child=Box(
                h_align="start",
                v_align="start",
                spacing=10,
                size=(350,-1),
                children=[
                    Image(pixbuf=app_info.get_icon_pixbuf(size=36)),
                    Box(
                        orientation="v",
                        children=[
                            Label(
                                app_info.display_name,
                                justfication="left",
                                h_align="start",
                                max_chars_width=25,
                                ellipsization="end",
                                name="appmenu-app-name",
                            ),
                            Label(
                                app_info.description if app_info.description else "",
                                justfication="left",
                                h_align="start",
                                max_chars_width=25,
                                ellipsization="end",
                                name="appmenu-app-desc",
                            ),
                        ],
                    ),
                ],
            ),
            **kwargs,
        )

    def launch_app(self):
        command = (
            " ".join(
                [arg for arg in self.app_info.command_line.split() if "%" not in arg]
            )
            if self.app_info.command_line
            else None
        )
        logger.info(f"Attempting to launch {self.app_info.name} with command {command}")
        exec_shell_command_async(
            f"hyprctl dispatch exec -- {command}",
            lambda *_: logger.info(f"Launched {self.app_info.name}"),
        ) if command else None

    def add_app_to_json(self) -> list:
        data = get_recent_apps()

        with open(APP_CACHE + "/last_launched.json", "w") as f:
            if self.app_info.name in data:
                data.remove(self.app_info.name)
            data.insert(0, self.app_info.name)
            data.pop() if len(data) > 7 else None
            json.dump(data, f)
            f.close()

        return data


class AppMenu(PopupWindow):
    def __init__(self, **kwargs):
        self.applications = sorted(
            get_desktop_applications(),
            key=lambda x: x.name.lower(),
        )
        self.application_buttons = {}
        self.buttons_box = Box(orientation="v", h_expand=True, v_expand=True)

        # Entry
        self.search_app_entry = Entry(
            name="appmenu-entry",
            style_classes=["cool-border"],
            placeholder="Enter To Search",
            editable=True,
            on_changed=self.on_entry_change,
            v_align="center",
            h_align="center",
        )

        self.search_app_entry.set_property("xalign", 0.5)

        # Scrolled Window
        self.scrolled_window = ScrolledWindow(
            name="appmenu-scroll",
            max_content_size=(-1, 540),
            min_content_size=(-1, 540),
            propagate_height=False,
            visible=False,
            child=self.buttons_box,
        )

        # Application buttons
        for app in self.applications:
            app_button = ApplicationButtonV2(app, on_clicked=self.on_app_launch)
            self.application_buttons[app.name] = app_button
            self.buttons_box.add(app_button)

        # Recent applications
        self.recent_applications = Box(
            orientation="v",
            h_align="start",
            v_align="start",
            h_expand=True,
            v_expand=True,
        )
        self.update_recent_apps()

        super().__init__(
            transition_duration=300,
            decorations="margin: 1px 1px 1px 0px;",
            anchor="center-left",
            transition_type="crossfade",
            child=Box(
                h_expand=True,
                v_expand=True,
                orientation="v",
                children=[
                    Box(
                        name="appmenu-corner",
                        children=Corner(
                            orientation="bottom-left",
                            size=50,
                        ),
                    ),
                    Box(
                        name="appmenu",
                        orientation="v",
                        spacing=20,
                        children=[
                            self.search_app_entry,
                            self.recent_applications,
                            self.scrolled_window,
                        ],
                    ),
                    Box(
                        name="appmenu-corner",
                        children=Corner(
                            orientation="top-left",
                            size=50,
                        ),
                    ),
                ],
            ),
            enable_inhibitor=True,
            keyboard_mode="on-demand",
        )

    def update_recent_apps(self, recent_apps: list | None = None):
        self.recent_applications.children = []
        recent_apps = get_recent_apps() if not recent_apps else recent_apps
        for app_id in recent_apps:
            [
                self.recent_applications.add(
                    ApplicationButtonV2(app, on_clicked=self.on_app_launch)
                )
                for app in self.applications
                if app.name == app_id
            ]

    def on_app_launch(self, app_button: ApplicationButtonV2, *_):
        app_button.launch_app()
        self.toggle_popup()
        self.update_recent_apps(app_button.add_app_to_json())

    # Overrides
    def toggle_popup(self, monitor: bool | None = None):
        self.search_app_entry.set_text("")
        self.search_app_entry.remove_style_class("active")
        self.scrolled_window.hide()
        self.recent_applications.show()
        self.search_app_entry.grab_focus()
        super().toggle_popup(monitor=True)

    def on_entry_change(self, entry: Entry):
        if entry.get_text() == " " or entry.get_text() == "":
            self.search_app_entry.remove_style_class("active")
            self.scrolled_window.hide()
            self.recent_applications.show()
            return
        self.scrolled_window.show()
        self.recent_applications.hide()
        self.search_app_entry.add_style_class(
            "active"
        ) if "active" not in self.search_app_entry.style_classes else None
        for child in self.buttons_box.children:
            self.reset_button(child)
        lister = process.extract(  # type: ignore
            entry.get_text(),
            self.application_buttons.keys(),
            scorer=fuzz.partial_ratio,
            limit=10,
        )

        for i, name in enumerate(lister):
            child = self.application_buttons[name[0]]
            self.buttons_box.reorder_child(child, i)
            GLib.timeout_add((i + 1) * 20, self.set_button, child)

    def set_button(self, child):
        child.set_style("animation-duration: 500ms;")
        child.add_style_class("shine")
        return False

    def reset_button(self, child):
        child.set_style("")
        child.remove_style_class("shine")
        return False
