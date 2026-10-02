# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A [Fabric](https://github.com/Fabric-Development/fabric) (Python GTK3 widget framework) configuration for a Wayland/Hyprland status bar and overlay windows, packaged for NixOS via flakes.

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
- `fabric_config/config.py` — module-level singleton services. Import `fabric_config.config as config` anywhere to access `config.audio`, `config.network` (AstalNetwork), `config.bluetooth_client`, `config.mprisplayer`, `config.brightness`, `config.sc` (screen recorder), `config.theme` (light/dark), `config.clipboard_history`. Services are initialized once at import time. Also holds shared helpers such as `audio_icon_name()`.

### Components (`fabric_config/components/`)

Top-level UI windows. All are `WaylandWindow` subclasses registered with the `Application`:

| Component | Description |
|---|---|
| `bar/bar.py` | `StatusBarSeperated` — the main top bar (workspaces, clock, system tray, quick settings) |
| `bar/widgets/` | Bar buttons and their popups (prayer times, clipboard history, power menu, temps, tray, battery) |
| `quick_settings/` | Quick settings popup panel (wifi/bluetooth toggles, sliders, media player, theme toggle) |
| `notification_popup.py` | Animated notification toasts using Cairo drawing |
| `overview.py` | Workspace overview with live window previews (`toplevel-streamer-rs`) |
| `dock.py` | Auto-hiding dock (Glace) with hover window previews |
| `app_menu.py` | Application launcher |
| `system_osd.py` | On-screen display for volume/brightness |
| `wallpaper_picker.py` | Wallpaper grid overlay (hyprpaper); tiles drawn by `widgets/rounded_cover_image.py` (also used for clipboard image cards) |
| `desktop_widget.py` | Desktop clock (`ClockWidget`) |

### Popup windows (`fabric_config/widgets/popup_window_v2.py`)

`PopupWindow` is the standard base for all overlay windows. It wraps content in a `PopupRevealer` (animated slide/fade via `Revealer`) and fills the screen with transparent `Padding` `EventBox` areas that dismiss the popup on click. Use `toggle_popup()` to show/hide; `popup_timeout()` for auto-dismissing popups (OSD pattern).

The older `fabric_config/snippits/popupwindow.py` uses a different approach (margin-based repositioning relative to a pointing widget; still used by the dock's preview) — prefer `popup_window_v2.py` for new components.

Popups use the shared commands-only Hyprland connection from `utils/hyprland_monitor.get_hyprland_monitors()`. Don't construct `Hyprland()`/`HyprlandWithMonitors()` per widget: each non-commands-only instance opens its own event-socket listener.

### Services (`fabric_config/services/`)

Custom GObject services built on `fabric.core.service.Service`. Use `@Property` and `@Signal` decorators. Key services:

- `brightness.py` — Screen/keyboard brightness (writes via `brightnessctl`, throttled)
- `mpris_v2.py` — `MprisPlayerManager` for media player control
- `screen_record.py` — Screen recording/screenshot via wf-recorder/slurp/hyprshot
- `clipboard_history.py` — cliphist-backed clipboard history
- `theme.py` — light/dark switching (GTK theme, icon theme, dconf)

Networking uses AstalNetwork (`config.network`) directly, plus the NM API for connecting/forgetting Wi-Fi (no `nmcli`, so passwords never appear in argv).

### Styling (`fabric_config/style/`)

SCSS, compiled with `sass` (dart-sass) at startup into `~/.cache/fabric/css/main.css` and loaded via `Application.set_stylesheet_from_file()`. Structure:

- `main.scss` / `main-light.scss` — entry points; each only picks a palette (`_dark-vars.scss` / `_light-vars.scss`) and uses `_base.scss`
- `_base.scss` — shared root rules; pulls in global classes and components
- `_tokens.scss` — radius/spacing scales and the GTK-safe `a()` (alpha) / `m()` (mix) functions (dart-sass would otherwise intercept `alpha()`/`mix()`)
- `_mixins.scss` — `bordered`, `panel`, `transition`
- `_global-classes.scss` — shared utility classes (`.button-basic`, `.button-border`, `.cool-border`, etc.)
- `components/` — per-component partials, registered in `components/_components.scss`

Palette variables live in a `:vars {}` block and are used as `var(--fg)`, `var(--accent)`, etc. (Fabric's CSS preprocessing; plain GTK3 has no CSS variables).

`apply_style` DBus action recompiles and hot-reloads CSS without restarting; Python changes need a restart.

### Utilities (`fabric_config/utils/`)

- `hyprland_monitor.py` — `HyprlandWithMonitors` for multi-monitor awareness; use the shared `get_hyprland_monitors()`
- `icon_resolver.py` — app icon lookup; use the shared `get_icon_resolver()` (instances share one cache file)
- `process.py` — `run_command_async(argv, callback(success, stdout, stderr))`
- `uri.py` — `file_uri_to_path()` (decodes `%20` etc.; don't slice `[7:]`)
- `accent.py` — accent color extraction from images
- `snippits/animator.py` — animation utility

Note: fabric's `exec_shell_command_async` only calls back per **stdout line** and never reads stderr. A command that prints nothing never triggers the callback, and failures go unnoticed. Use `run_command_async` when you need completion or error handling. For long-running chatty processes (e.g. wf-recorder), silence their output rather than piping it unread.

## gi.repository type stubs

Type stubs come from `pygobject-stubs`, pinned to GTK3 (`PYGOBJECT_STUB_CONFIG = "Gtk3,Gdk3"`) in the `flake.nix` overlay. Don't add `ps.pygobject-stubs` in `shell.nix`: that pulls in the unpinned GTK4 build and conflicts. The same override marks the stubs `partial` (so `gi._propertyhelper` etc. resolve to the real `gi`, which Fabric's `Property` needs) and copies in stubs for typelibs it lacks, generated by `nix/gi-extra-stubs.nix`. To stub a new typelib, add it to `modules` there (and its library to `buildInputs`). Don't merge extra stubs in through `python.withPackages`: that turns `gi-stubs/` into a directory of symlinks, which basedpyright then ignores. Stubs for non-gi modules without their own (e.g. the `hyprland_toplevel_streamer` pyo3 extension) live in `typings/`.

basedpyright settings are in `pyproject.toml` (`[tool.basedpyright]`), which makes editors ignore their own `basedpyright.analysis.*` settings, so set the mode there. It honours `# type: ignore`, and the `Property` getters need return annotations: without one, a getter that returns an attribute its setter assigns makes basedpyright lose the decorator ("Cannot access attribute "setter" for class "FunctionType"").

`gi.require_version(...)` must precede the matching `from gi.repository import ...`; mark those imports `# noqa: E402`.

## Nix notes

- Python version is controlled by `pythonPackagesAttr = "python314Packages"` in `flake.nix` — change this one value to switch Python versions.
- Nix formatter: `nixfmt-rfc-style` (run `nix fmt`).
- The package is built via `derivation.nix`; the `fabric-config` script entrypoint is defined in `pyproject.toml`.
