import json
import os
import re

import gi
from loguru import logger

gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf, GLib, Gtk  # noqa: E402


# TODO WIP
# Idea: nearest string matching algorithm
#       if already exists: retrieve from json
#       if found: stor in json: app_id -> icon_name
#       if not found: store in json -> misisng-icon


CACHE_DIR = str(GLib.get_user_cache_dir()) + "/fabric"
ICON_CACHE_FILE = CACHE_DIR + "/icons.json"
STEAM_LIBRARY_CACHE = GLib.get_user_data_dir() + "/Steam/appcache/librarycache"

# Proton/XWayland Steam games get the window class "steam_app_<appid>"
_STEAM_APP_RE = re.compile(r"steam_app_(\d+)")
# Steam keeps each game's 32px client icon as "<sha1>.jpg" in its library cache
_STEAM_CLIENT_ICON_RE = re.compile(r"[0-9a-f]{40}\.jpg")
# too generic to match a desktop file name by
_GENERIC_WORDS = {"app", "apps", "bin", "com", "desktop", "org"}
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)


class IconResolver:
    def __init__(
        self, default_applicaiton_icon: str = "application-x-executable-symbolic"
    ):
        self._icon_dict: dict[str, str] = {}
        if os.path.exists(ICON_CACHE_FILE):
            try:
                with open(ICON_CACHE_FILE) as f:
                    self._icon_dict = json.load(f)
            except (OSError, json.JSONDecodeError):
                logger.info("[ICONS] Cache file is unreadable or corrupted, resetting")

        self.default_applicaiton_icon = default_applicaiton_icon

    def get_icon_name(self, app_id: str):
        if match := _STEAM_APP_RE.fullmatch(app_id):
            # not cached on disk: the icon may only appear once Steam fetches it
            return self._steam_icon(match.group(1))
        if app_id in self._icon_dict:
            return self._icon_dict[app_id]
        new_icon = self._compositor_find_icon(app_id)
        logger.info(
            f"[ICONS] found new icon: '{new_icon}' for app id: '{app_id}', storing..."
        )
        self._store_new_icon(app_id, new_icon)
        return new_icon

    def get_icon_pixbuf(self, app_id: str, size: int = 16):
        icon = self.get_icon_name(app_id)
        try:
            # desktop files may give an absolute path instead of an icon name
            if os.path.isabs(icon):
                return GdkPixbuf.Pixbuf.new_from_file_at_size(icon, size, size)
            return Gtk.IconTheme.get_default().load_icon(
                icon, size, Gtk.IconLookupFlags.FORCE_SIZE
            )
        except GLib.Error:
            return Gtk.IconTheme.get_default().load_icon(
                self.default_applicaiton_icon, size, Gtk.IconLookupFlags.FORCE_SIZE
            )

    def _store_new_icon(self, app_id: str, icon: str):
        self._icon_dict[app_id] = icon
        with open(ICON_CACHE_FILE, "w") as f:
            json.dump(self._icon_dict, f)
            f.close()

    def _get_icon_from_desktop_file(self, desktop_file_path: str):
        # TODO: get icon in the [Desktop Entry] section only
        with open(desktop_file_path) as f:
            for line in f.readlines():
                if line.startswith("Icon="):
                    return line[5:].strip()
            return self.default_applicaiton_icon

    def _get_desktop_file(self, app_id: str) -> str | None:
        data_dirs = [GLib.get_user_data_dir(), *GLib.get_system_data_dirs()]
        for data_dir in data_dirs:
            data_dir = data_dir + "/applications/"
            if os.path.exists(data_dir):
                # Do name resolving here

                files = os.listdir(data_dir)
                matching = [
                    s for s in files if "".join(app_id.lower().split()) in s.lower()
                ]
                if matching:
                    return data_dir + matching[0]

                for word in re.split(r"-|\.|_|\s", app_id):
                    if (
                        len(word) < 3
                        or word.isdigit()
                        or word.lower() in _GENERIC_WORDS
                    ):
                        continue
                    matching = [s for s in files if word.lower() in s.lower()]
                    if matching:
                        return data_dir + matching[0]

        return None

    def _steam_icon(self, steam_app_id: str) -> str:
        # Steam's own windows (e.g. its web helper) use app id 0
        if steam_app_id == "0":
            return "steam"
        # installed with a desktop shortcut for the game
        if Gtk.IconTheme.get_default().has_icon(f"steam_icon_{steam_app_id}"):
            return f"steam_icon_{steam_app_id}"
        cache_dir = f"{STEAM_LIBRARY_CACHE}/{steam_app_id}"
        try:
            for name in os.listdir(cache_dir):
                if _STEAM_CLIENT_ICON_RE.fullmatch(name):
                    return f"{cache_dir}/{name}"
        except OSError:
            pass
        return "steam"

    def _compositor_find_icon(self, app_id: str):
        if Gtk.IconTheme.get_default().has_icon(app_id):
            return app_id
        if Gtk.IconTheme.get_default().has_icon(app_id + "-desktop"):
            return app_id + "-desktop"
        desktop_file = self._get_desktop_file(app_id)
        return (
            self._get_icon_from_desktop_file(desktop_file)
            if desktop_file
            else self.default_applicaiton_icon
        )


_shared_resolver: IconResolver | None = None


def get_icon_resolver() -> IconResolver:
    """
    The shared IconResolver. Use this rather than constructing one: every
    instance writes the same cache file and would overwrite the others' entries.
    """
    global _shared_resolver
    if _shared_resolver is None:
        _shared_resolver = IconResolver()
    return _shared_resolver
