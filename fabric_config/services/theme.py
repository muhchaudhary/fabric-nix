import os
import subprocess
from pathlib import Path

from fabric.core.service import Property, Service
from gi.repository import GLib

_CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "fabric")
_THEME_FILE = os.path.join(_CONFIG_DIR, "theme")
os.makedirs(_CONFIG_DIR, exist_ok=True)

_GTK_INI = """\
[Settings]
gtk-cursor-theme-name=Bibata-Modern-Classic
gtk-cursor-theme-size=24
gtk-icon-theme-name={icon_theme}
gtk-theme-name={gtk_theme}
"""


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
        self._apply_gtk_theme(self._is_light)

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
        self._apply_gtk_theme(value)
        self.notify("is-light")

    def _apply_gtk_theme(self, light: bool):
        gtk_theme = "Colloid-Light" if light else "Colloid-Dark"
        icon_theme = "kora-light" if light else "kora"
        color_scheme = "prefer-light" if light else "prefer-dark"

        for path, value in [
            ("/org/gnome/desktop/interface/color-scheme", color_scheme),
            ("/org/gnome/desktop/interface/gtk-theme", gtk_theme),
            ("/org/gnome/desktop/interface/icon-theme", icon_theme),
        ]:
            try:
                subprocess.Popen(
                    ["dconf", "write", path, f"'{value}'"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

        # home-manager generates these as read-only symlinks; break and rewrite
        ini = _GTK_INI.format(gtk_theme=gtk_theme, icon_theme=icon_theme)
        config_dir = Path(GLib.get_user_config_dir())
        for gtk_ver in ("gtk-3.0", "gtk-4.0"):
            settings_path = config_dir / gtk_ver / "settings.ini"
            try:
                if settings_path.exists() or settings_path.is_symlink():
                    settings_path.unlink()
                settings_path.write_text(ini)
            except Exception:
                pass

        # GTK4 ignores gtk-theme-name entirely; it loads theme CSS via gtk.css.
        # home-manager writes a symlink here importing Colloid-Dark from the nix store.
        # Resolve the actual CSS path via the nix profile so it stays correct after upgrades.
        gtk4_css_path = config_dir / "gtk-4.0" / "gtk.css"
        theme_css = (
            Path.home() / f".nix-profile/share/themes/{gtk_theme}/gtk-4.0/gtk.css"
        )
        if theme_css.exists():
            css_content = (
                "/** GTK 4 reads the theme configured by gtk-theme-name, but ignores it.\n"
                " * It does however respect user CSS, so import the theme from here.\n"
                "**/\n"
                f'@import url("file://{theme_css.resolve()}");\n'
            )
            try:
                if gtk4_css_path.exists() or gtk4_css_path.is_symlink():
                    gtk4_css_path.unlink()
                gtk4_css_path.write_text(css_content)
            except Exception:
                pass

    def toggle(self):
        self.is_light = not self._is_light
