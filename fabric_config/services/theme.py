import os

from fabric.core.service import Property, Service
from gi.repository import GLib

_CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "fabric")
_THEME_FILE = os.path.join(_CONFIG_DIR, "theme")
os.makedirs(_CONFIG_DIR, exist_ok=True)


def _load_theme() -> bool:
    try:
        with open(_THEME_FILE) as f:
            return f.read().strip() == "light"
    except Exception:
        return False


class ThemeService(Service):
    def __init__(self, **kwargs):
        self._is_light = _load_theme()
        super().__init__(**kwargs)

    @Property(bool, "read-write", default_value=False)
    def is_light(self) -> bool:  # type: ignore
        return self._is_light

    @is_light.setter
    def is_light(self, value: bool):
        if value == self._is_light:
            return
        self._is_light = value
        try:
            with open(_THEME_FILE, "w") as f:
                f.write("light" if value else "dark")
        except Exception:
            pass
        self.notify("is-light")

    def toggle(self):
        self.is_light = not self._is_light
