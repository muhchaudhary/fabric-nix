from typing import TypedDict
import gi
import os
import json

from fabric.widgets.box import Box
from fabric.widgets.image import Image
from fabric.widgets.button import Button

from fabric.widgets.wayland import WaylandWindow
from fabric import Application

gi.require_version("Glace", "0.1")
from gi.repository import GLib, Glace, Gtk
from loguru import logger


# Idea: nearest string matching algorithm
#       if already exists: retrieve from json
#       if found: stor in json: app_id -> icon_name
#       if not found: store in json -> misisng-icon


CACHE_DIR = str(GLib.get_user_cache_dir()) + "/fabric"
ICON_CACHE_FILE = CACHE_DIR + "/icons.json"


class IconResolver:
    def __init__(self):
        if os.path.exists(ICON_CACHE_FILE):
            f = open(ICON_CACHE_FILE)
            try:
                self._icon_dict = json.load(f)
            except json.JSONDecodeError:
                logger.info("[ICONS] Cache file does not exist or is corrupted")
            f.close()
        else:
            self._icon_dict = {}

    def get_icon(self, app_id: str):
        if app_id in self._icon_dict:
            return self._icon_dict[app_id]
        new_icon = self._compositor_find_icon(app_id)
        logger.info(f"[ICONS] found new icon: '{new_icon}' for app id: '{app_id}', storing...")
        self._store_new_icon(app_id, new_icon)
        return new_icon

    def _store_new_icon(self, app_id: str, icon: str):
        self._icon_dict[app_id] = icon
        with open(ICON_CACHE_FILE, "w") as f:
            json.dump(self._icon_dict, f)
            f.close()

    def _get_icon_from_desktop_file(self, desktop_file_path: str):
        with open(desktop_file_path) as f:
            for line in f.readlines():
                if "Icon=" in line:
                    return "".join(line[5:].split())
            return "application-x-symbolic"

    def _get_desktop_file(self, app_id: str) -> str | None:
        data_dirs = GLib.get_system_data_dirs()
        for data_dir in data_dirs:
            data_dir = data_dir + "/applications/"
            if os.path.exists(data_dir):
                # Do name resolving here

                # try the most basic one first
                # TODO: implement a search algorithm to find the nearest icon from app_id
                files = os.listdir(data_dir)
                desktop_file_path = data_dir + app_id + ".desktop"
                if os.path.exists(desktop_file_path):
                    return desktop_file_path

                desktop_file_path = data_dir + app_id.lower() + ".desktop"
                if os.path.exists(desktop_file_path):
                    return desktop_file_path

                # remove whitespace, lowercase: code - insiders
                desktop_file_path = (
                    data_dir + "".join(app_id.lower().split()) + ".desktop"
                )

                # Check every element inside:
                app_id_parts = app_id.split()

                for part in app_id_parts:
                    if
                if os.path.exists(desktop_file_path):
                    return desktop_file_path
        return None

    def _compositor_find_icon(self, app_id: str):
        if Gtk.IconTheme.get_default().has_icon(app_id):
            return app_id
        if Gtk.IconTheme.get_default().has_icon(app_id + "-desktop"):
            return app_id + "-desktop"
        desktop_file = self._get_desktop_file(app_id)
        return (
            self._get_icon_from_desktop_file(desktop_file)
            if desktop_file
            else "application-x-symbolic"
        )


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
            lambda *_: client_image.set_from_icon_name(
                self.icon_resolver.get_icon(client.get_app_id())
            ),
        )
        client.bind_property("title", client_button, "tooltip-text", 0)
        client_button.connect("button-press-event", lambda *_: client.activate())

        self.add(client_button)

        client.connect("close", lambda *_: self.remove(client_button))
