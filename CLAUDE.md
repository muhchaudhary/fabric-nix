# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A [Fabric](https://github.com/Fabric-Development/fabric) (Python GTK4 widget framework) configuration for a Wayland/Hyprland status bar and overlay windows, packaged for NixOS via flakes.

## Development environment

The dev environment is managed by Nix flakes + direnv. After cloning:

```bash
direnv allow   # builds and loads the dev shell automatically
```

The shell provides Python 3.14, `ruff` (linter), `basedpyright` (LSP/type checker), and all GTK/GObject dependencies. **Python packages are not installed globally** — they are only available inside the direnv shell.

To use the devshell from outside this directory (e.g., in scripts), see the `direnv_cd` pattern in `readme.md`.

## Running

```bash
python run_fabric.py          # start the bar
```

While running, send commands via DBus:

```bash
dbus-send --session --print-reply --dest=org.Fabric.fabric \
  /org/Fabric/fabric org.Fabric.fabric.Evaluate string:"toggle_appmenu()"
```

Available actions are registered in `fabric_config/main.py` with `@the_app.action()`.

## Linting and type checking

```bash
ruff check .          # lint
ruff format .         # format
basedpyright .        # type check
```

## Architecture

### Entry points

- `run_fabric.py` → `fabric_config/main.py:main()` — creates `MyApp(Application)`, registers DBus actions, starts the GTK main loop.
- `fabric_config/config.py` — module-level singleton services. Import `fabric_config.config as config` anywhere to access `config.audio`, `config.network`, `config.bluetooth_client`, `config.mprisplayer`, `config.brightness`, `config.sc` (screen recorder). Services are initialized once at import time.

### Components (`fabric_config/components/`)

Top-level UI windows. All are `WaylandWindow` subclasses registered with the `Application`:

| Component | Description |
|---|---|
| `bar/bar.py` | `StatusBarSeperated` — the main top bar (workspaces, clock, system tray, quick settings) |
| `quick_settings/` | Quick settings popup panel (wifi/bluetooth toggles, sliders, media player) |
| `notification_popup.py` | Animated notification toasts using Cairo drawing |
| `overview.py` | App overview window |
| `app_menu.py` | Application launcher |
| `system_osd.py` | On-screen display for volume/brightness |
| `wallpaper_picker.py` | Wallpaper selection overlay |

### Popup windows (`fabric_config/widgets/popup_window_v2.py`)

`PopupWindow` is the standard base for all overlay windows. It wraps content in a `PopupRevealer` (animated slide/fade via `Revealer`) and fills the screen with transparent `Padding` `EventBox` areas that dismiss the popup on click. Use `toggle_popup()` to show/hide; `popup_timeout()` for auto-dismissing popups (OSD pattern).

The older `fabric_config/snippits/popupwindow.py` uses a different approach (margin-based repositioning relative to a pointing widget) — prefer `popup_window_v2.py` for new components.

### Services (`fabric_config/services/`)

Custom GObject services built on `fabric.core.service.Service`. Use `@Property` and `@Signal` decorators. Key services:

- `wifi.py` — `Wifi`, `Ethernet`, `NetworkClient` wrapping NetworkManager via GObject introspection
- `brightness.py` — Screen brightness control
- `mpris_v2.py` — `MprisPlayerManager` for media player control
- `screen_record.py` — Screen recording/screenshot via wf-recorder/hyprshot

### Styling (`fabric_config/style/`)

CSS loaded via `Application.set_stylesheet_from_file()`. Structure:

- `main.css` — root file, imports everything
- `colors.css` — CSS custom properties (`--accent`, `--fg-test`, `--bg`, etc.)
- `global-classes.css` — shared utility classes (`.button-basic`, `.button-border`, `.cool-border`, etc.)
- `components/` — per-component CSS files

`apply_style` DBus action hot-reloads CSS without restarting.

### Utilities (`fabric_config/utils/`)

- `hyprland_monitor.py` — `HyprlandWithMonitors` for multi-monitor awareness in popup positioning
- `icon_resolver.py` — app icon lookup
- `accent.py` — accent color extraction from wallpaper
- `bezier.py` / `snippits/animator.py` — animation utilities

## gi.repository type stubs

`gi.repository` imports lack type checking by default. Stubs are generated via `gengir` (see `nix/gengir.nix` and `nix/generate_gi_stubs.sh`). The Fabric wiki has more detail: https://fabric-development.github.io/fabric-wiki/installing-stubs.html

## Nix notes

- Python version is controlled by `pythonPackagesAttr = "python314Packages"` in `flake.nix` — change this one value to switch Python versions.
- Nix formatter: `nixfmt-rfc-style` (run `nix fmt`).
- The package is built via `derivation.nix`; the `fabric-config` script entrypoint is defined in `pyproject.toml`.
