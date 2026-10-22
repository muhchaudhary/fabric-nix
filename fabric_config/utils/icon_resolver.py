import json
import os
import re

import gi
from loguru import logger

gi.require_version("Gtk", "3.0")
# GLib 2.86 moved DesktopAppInfo out of Gio
gi.require_version("GioUnix", "2.0")
from gi.repository import GdkPixbuf, Gio, GioUnix, GLib, Gtk  # noqa: E402

CACHE_DIR = str(GLib.get_user_cache_dir()) + "/fabric"
ICON_CACHE_FILE = CACHE_DIR + "/icons.json"
# bump when resolving changes, so entries found the old way are dropped
CACHE_VERSION = 2
STEAM_LIBRARY_CACHE = GLib.get_user_data_dir() + "/Steam/appcache/librarycache"

# Proton/XWayland Steam games get the window class "steam_app_<appid>";
# "steam_proton" is Proton's own helper window
_STEAM_APP_RE = re.compile(r"steam_(?:app_(\d+)|proton)")
# Steam keeps each game's 32px client icon as "<sha1>.jpg" in its library cache
_STEAM_CLIENT_ICON_RE = re.compile(r"[0-9a-f]{40}\.jpg")
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)


def _unwrap(app_id: str) -> str:
    # NixOS wrappers rename the binary to ".<name>-wrapped", and so its class;
    # Wine/Proton windows are classed by the Windows executable
    return app_id.removeprefix(".").removesuffix("-wrapped").removesuffix(".exe")


class IconResolver:
    def __init__(
        self, default_applicaiton_icon: str = "application-x-executable-symbolic"
    ):
        # confident matches (icon theme, StartupWMClass, desktop ID): kept on disk
        self._icon_dict: dict[str, str] = {}
        # search guesses and misses: kept for this session only, so a newly
        # installed app or a better match is picked up on the next start
        self._guesses: dict[str, str] = {}
        if os.path.exists(ICON_CACHE_FILE):
            try:
                with open(ICON_CACHE_FILE) as f:
                    data = json.load(f)
                if data.get("version") == CACHE_VERSION:
                    self._icon_dict = data["icons"]
            except (OSError, json.JSONDecodeError, AttributeError, KeyError):
                logger.info("[ICONS] Cache file is unreadable or corrupted, resetting")

        self.default_applicaiton_icon = default_applicaiton_icon

        # desktop entries by lowercased StartupWMClass and desktop ID, built on
        # first use and dropped when apps are installed or removed
        self._by_wm_class: dict[str, GioUnix.DesktopAppInfo] | None = None
        self._by_id: dict[str, GioUnix.DesktopAppInfo] | None = None
        self._app_monitor = Gio.AppInfoMonitor.get()
        self._app_monitor.connect("changed", lambda *_: self._clear())
        Gtk.IconTheme.get_default().connect("changed", lambda *_: self._clear())

    def get_icon_name(self, app_id: str):
        if not app_id:
            return self.default_applicaiton_icon
        if match := _STEAM_APP_RE.fullmatch(app_id):
            # not cached on disk: the icon may only appear once Steam fetches it
            return self._steam_icon(match.group(1) or "0")
        if app_id in self._icon_dict:
            return self._icon_dict[app_id]
        if app_id in self._guesses:
            return self._guesses[app_id]

        icon = self._find_icon(app_id)
        if icon:
            logger.info(f"[ICONS] found icon '{icon}' for app id '{app_id}'")
            self._store_new_icon(app_id, icon)
            return icon
        icon = self._search_icon(app_id) or self.default_applicaiton_icon
        logger.info(f"[ICONS] guessed icon '{icon}' for app id '{app_id}'")
        self._guesses[app_id] = icon
        return icon

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

    def _clear(self):
        self._by_wm_class = self._by_id = None
        self._guesses.clear()
        if self._icon_dict:
            self._icon_dict.clear()
            self._save()

    def _store_new_icon(self, app_id: str, icon: str):
        self._icon_dict[app_id] = icon
        self._save()

    def _save(self):
        with open(ICON_CACHE_FILE, "w") as f:
            json.dump({"version": CACHE_VERSION, "icons": self._icon_dict}, f)

    def _index_apps(self):
        self._by_wm_class, self._by_id = {}, {}
        # listed apps first, so they win over hidden helpers sharing a class
        apps = sorted(Gio.AppInfo.get_all(), key=lambda a: not a.should_show())
        for app in apps:
            if not isinstance(app, GioUnix.DesktopAppInfo):
                continue
            if wm_class := app.get_startup_wm_class():
                self._by_wm_class.setdefault(wm_class.lower(), app)
            if app_id := app.get_id():
                self._by_id.setdefault(app_id.lower().removesuffix(".desktop"), app)

    def _app_icon(self, app: Gio.AppInfo) -> str | None:
        """The app's icon, if the theme has it or its file exists."""
        icon = app.get_icon()
        if isinstance(icon, Gio.FileIcon):
            path = icon.get_file().get_path()
            return path if path and os.path.exists(path) else None
        if isinstance(icon, Gio.ThemedIcon):
            theme = Gtk.IconTheme.get_default()
            return next((n for n in icon.get_names() if theme.has_icon(n)), None)
        return None

    def _find_icon(self, app_id: str) -> str | None:
        """An icon matched exactly, by icon name, StartupWMClass or desktop ID."""
        if self._by_wm_class is None or self._by_id is None:
            self._index_apps()
        assert self._by_wm_class is not None and self._by_id is not None
        theme = Gtk.IconTheme.get_default()
        for name in dict.fromkeys([app_id, _unwrap(app_id)]):
            for icon in (name, name.lower(), name + "-desktop"):
                if theme.has_icon(icon):
                    return icon
            for index in (self._by_wm_class, self._by_id):
                app = index.get(name.lower())
                if app and (icon := self._app_icon(app)):
                    return icon
        return None

    def _search_icon(self, app_id: str) -> str | None:
        """
        A guess from GIO's desktop entry search, taken only when one listed app
        ranks above the rest and has every word of the app id as a whole word
        of its name, desktop ID or executable (search also matches prefixes,
        comments and keywords: "Code" finds a URL handler, "explorer" a file
        manager).
        """
        words = re.split(r"[^a-z0-9]+", _unwrap(app_id).lower())
        words = [w for w in words if w]
        if not words:
            return None
        for group in GioUnix.DesktopAppInfo.search(" ".join(words)):
            apps = []
            for desktop_id in group:
                try:
                    app = GioUnix.DesktopAppInfo.new(desktop_id)
                except TypeError:  # removed since GIO indexed it
                    continue
                if app.should_show():
                    apps.append(app)
            if not apps:
                continue
            if len(apps) > 1:
                return None
            app = apps[0]
            text = f"{app.get_name()} {app.get_id()} {app.get_executable()}"
            if set(words) <= set(re.split(r"[^a-z0-9]+", text.lower())):
                return self._app_icon(app)
            return None
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
