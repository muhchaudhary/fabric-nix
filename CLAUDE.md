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
- `fabric_config/config.py` — module-level singleton services. Import `fabric_config.config as config` anywhere to access `config.audio`, `config.audio_devices` (outputs/inputs to switch between), `config.network` (AstalNetwork), `config.bluetooth_client`, `config.mprisplayer`, `config.brightness`, `config.sc` (screen recorder), `config.theme` (light/dark), `config.clipboard_history`, `config.wallpaper_accent` (wallpaper colours; drives the theme accent), `config.notifications` (notification server + history), `config.window_previews` (live window previews), `config.hyprsunset` (night light), `config.caffeine` (idle lock), `config.power_profiles` (power-profiles-daemon), `config.system_stats` (load and sensors). Services are initialized once at import time. Also holds shared helpers such as `audio_icon_name()`.

### Components (`fabric_config/components/`)

Top-level UI windows. All are `WaylandWindow` subclasses registered with the `Application`:

| Component | Description |
|---|---|
| `bar/bar.py` | `StatusBarSeperated` — the main top bar (workspaces, clock, system tray, quick settings) |
| `bar/island.py` | `DynamicIsland`, the bar's centre: workspaces plus a now-playing chip; grows to announce things (`show_event(icon, title, subtitle)`; new tracks, recording, caffeine, DND) and opens a media view (controls, current lyric) when the chip is hovered. A `Gtk.Stack` with `interpolate_size`; views share the bar's height (`vhomogeneous`) so the bar's exclusive zone never changes. Media comes from the desktop's shared `get_media_state()` |
| `bar/widgets/` | Bar buttons and their popups (prayer times (`prayer_times.py`; `prayer_extras.py`: Qibla compass, optional adhan from `~/.local/share/fabric/adhan.mp3` / `adhan-<prayer>.mp3` (a chime without one; `stop_adhan` action), Ramadan Iftar/Suhoor countdown on the button; the service's `prayer-time` signal fires when a prayer begins and the island announces it), clipboard history, power menu, temps + system monitor popup (`stats.py`: CPU/memory/GPU/network sparklines, disk, top processes), recording indicator, tray, battery) |
| `quick_settings/` | Quick settings popup panel (wifi/bluetooth toggles, night light + theme toggles, DND, caffeine, record, screenshot, a power-profile row when power-profiles-daemon runs, sliders, media player; the volume slider's arrow opens the sound panel: per-app volume, output and input pickers) |
| `notification_popup.py` | Notification toasts (cards fly in/out on a click-through overlay that's only mapped while animating). Timing out only hides a toast; max 4 shown, critical ones stay until dismissed |
| `bar/widgets/notification_center.py` | Notification center: bell button + popup listing notifications grouped by app, Do Not Disturb, clear (actions `toggle_notification_center`, `toggle_do_not_disturb`). Cards come from `widgets/notification_card.py` |
| `overview.py` | Workspace overview with live window previews (`config.window_previews`, while open) |
| `dock.py` | Auto-hiding dock: one icon per app (Glace), dots per window, click focuses/cycles. Hover previews list the app's windows from Hyprland, live via `config.window_previews` while open. One fixed-height, full-width window whose input region covers only what's showing; don't let it resize, or the region lags and the dock hides under the pointer |
| `app_menu.py` | Application launcher (search, frecency, pins/hidden apps, `=` calc and unit conversion, `>` run, `:` emoji, `?` web search, `#` colours + hyprpicker, `@` windows: focus, right-click to close/kill); logic in `utils/app_search.py` and `utils/units.py` |
| `radial_menu.py` | `RadialMenu`: a ring of quick actions around the pointer (action `toggle_radial_menu`; items in `main.py:_radial_items`). A full-monitor overlay (exclusive zone -1, so pointer coordinates from `j/cursorpos` minus the monitor's origin line up); drawn in cairo from `#radial-menu`'s CSS colours and `@accent`. Click a slice, press 1-8 or arrows + Enter, Escape or click outside to close |
| `system_osd.py` | On-screen display for volume, mic mute, brightness and keyboard backlight; pops up on service changes (the `toggle_system_osd` action still works), hover to keep open, scroll to adjust, click to mute |
| `wallpaper_picker.py` | Wallpaper grid overlay (hyprpaper; header has the slideshow controls: `services/wallpaper_slideshow.py`, `config.wallpaper_slideshow`, a shuffled wallpaper every 15 min to 3 h, by day from the brighter half and after sunset the darker half, measured once with Pillow and cached; it switches at sunrise/sunset but leaves a hand-picked one until its turn); tiles drawn by `widgets/rounded_cover_image.py` (also used for clipboard image cards) |
| `desktop/` | The desktop: `DesktopManager` makes one full-screen bottom-layer `DesktopWindow` per monitor with a macOS-style clock (digital/analog/word faces, click for a focus timer), info lines (next prayer, weather via Open-Meteo, Hijri date, greeting, "on this day"), and a music player card in its own window per monitor (`music_player.py`: a simple card drawn in cairo after the "Elegant Music Player" Rainmeter skin, with synced lyrics from LRCLIB and a switchable, seekable MPRIS player from `media.py`; dragging moves the window via its layer-shell margins), sticky notes, and a drawn layer (weather from Open-Meteo's code: rain, snow, storm flashes, fog/cloud haze, stars on a clear night (`weather_fx.py`; haze is drawn at 1/8 size, slow kinds at 10 fps; `preview_weather` DBus action shows one for 30 s); prayer arc, cava visualizer) that only animates while that monitor's desktop is showing (`visibility.py`). Each piece is its own overlay child (no full-screen click-through layers: GTK passes clicks through their children too). Right-click it for the menu; choices persist via `settings.py`. Legibility: each window measures its monitor's wallpaper (`utils/wallpaper_map.py`: brightness and busyness of any rectangle, as hyprpaper's cover fit shows it), picks light or dark clock text from what's actually behind the clock, draws a soft scrim (`fx.py`) where it's busy or mid-toned, and with position "auto" (the default) moves the clock to the calmest readable spot, near the top centre, with hysteresis. Sized from each monitor's height |

### Popup windows (`fabric_config/widgets/popup_window_v2.py`)

`PopupWindow` is the standard base for all overlay windows. It wraps content in a `PopupRevealer` (animated slide/fade via `Revealer`) and fills the screen with transparent `Padding` `EventBox` areas that dismiss the popup on click. Use `toggle_popup()` to show/hide; `popup_timeout()` for auto-dismissing popups (OSD pattern).

Popups use the shared commands-only Hyprland connection from `utils/hyprland_monitor.get_hyprland_monitors()`. Don't construct `Hyprland()`/`HyprlandWithMonitors()` per widget: each non-commands-only instance opens its own event-socket listener.

### Services (`fabric_config/services/`)

Custom GObject services built on `fabric.core.service.Service`. Use `@Property` and `@Signal` decorators. Key services:

- `brightness.py` — Screen/keyboard brightness (writes via `brightnessctl`, throttled)
- `mpris_v2.py` — `MprisPlayerManager` for media player control. `play_pause()` reports the expected status at once until the player confirms it; `fetch_position()` reads the live position (the cached `Position` goes stale)
- `screen_record.py` — Screen recording/screenshot via wf-recorder/slurp/hyprshot. Keeps the wf-recorder process: `recording` (False) fires whenever it exits, however it ends; `recording_since` is its start (monotonic). Fullscreen records the focused monitor (`-o`: with several, wf-recorder would prompt on stdin and quit)
- `clipboard_history.py` — cliphist-backed clipboard history
- `cava.py` — shared cava audio levels (`config.cava`); callers `set_wanted(owner, bool)` and it runs while anyone wants it
- `theme.py` — light/dark switching (GTK theme, icon theme, dconf)
- `notifications.py` — `NotificationCenter` (`config.notifications`): owns fabric's notification server and keeps the history, saved to `~/.cache/fabric/notifications.json`. Notifications stay live (actions work) until dismissed; `replaces_id` updates in place; restored entries have negative ids and no actions
- `window_previews.py` — `WindowPreviews` (`config.window_previews`): live window previews via toplevel-streamer-rs's `PreviewHub` (a Rust thread captures each subscribed window when it redraws, capped by `fps`, downscaled, as premultiplied BGRA = cairo ARGB32; delivered through an eventfd watched by GLib). `subscribe(owner, address, w, h, on_frame, fps)` / `unsubscribe(owner)`; use `cover_size()` to pick the frame size and `RoundedCoverImage.set_surface()` to draw. Unsubscribe when the preview hides: subscribed windows are captured continuously
- `audio_devices.py` — `AudioDevices` (`config.audio_devices`): Cvc's UI devices (what GNOME's sound settings list: one per sink port, so a laptop's speakers and headphone jack are separate, plus Bluetooth profiles and unused HDMI ports). `select(device)` switches port/profile/sink as needed. It has its own `Cvc.MixerControl`, since fabric's `Audio` keeps its control private and Cvc only announces devices as they're added
- `hyprsunset.py` — `Hyprsunset` (`config.hyprsunset`): night light via `hyprctl hyprsunset` (temperature, gamma, `identity` when off). hyprsunset can't report whether it's filtering, so on/off, temperature and gamma are kept here, saved to `~/.cache/fabric/hyprsunset.json` and pushed on startup; commands go one at a time with only the latest state sent (slider drags)
- `caffeine.py` — `Caffeine` (`config.caffeine`): keeps the screen awake by holding a logind `idle` inhibitor fd (hypridle honours it); closing the fd, or fabric exiting, releases it
- `power_profiles.py` — `PowerProfiles` (`config.power_profiles`): power-profiles-daemon over DBus; `available` is False without it
- `system_stats.py` — `SystemStats` (`config.system_stats`): psutil + NVML (`utils/nvml.py`, ctypes; no `nvidia-smi` processes) sampled each second on a thread, `updated(sample)` on the main thread, a minute of `history` per metric. Top processes only while someone `set_wanted(owner, True)`
- `wallpaper_accent.py` — dominant colour of each monitor's wallpaper (Pillow at reduced size, off the main thread; ColorThief is pure Python and blocks the GTK loop on large images) and the theme accent made from it

Networking uses AstalNetwork (`config.network`) directly, plus the NM API for connecting/forgetting Wi-Fi (no `nmcli`, so passwords never appear in argv).

### Styling (`fabric_config/style/`)

SCSS, compiled with `sass` (dart-sass) at startup into `~/.cache/fabric/css/main.css` and loaded via `Application.set_stylesheet_from_file()`. Structure:

- `main.scss` / `main-light.scss` — entry points; each only picks a palette (`_dark-vars.scss` / `_light-vars.scss`) and uses `_base.scss`
- `_base.scss` — shared root rules; pulls in global classes and components
- `_tokens.scss` — radius/spacing scales and the GTK-safe `a()` (alpha) / `m()` (mix) functions (dart-sass would otherwise intercept `alpha()`/`mix()`)
- `_mixins.scss` — `glass` (tint, hairline edge, bright top rim), `panel` (glass + padding), `floating-shadow`, `bordered`, `transition`
- `_global-classes.scss` — shared utility classes (`.button-basic`, `.button-border`, `.cool-border`, etc.)
- `components/` — per-component partials, registered in `components/_components.scss`

Palette variables live in a `:vars {}` block and are used as `var(--fg)`, `var(--accent)`, etc. (Fabric's CSS preprocessing; plain GTK3 has no CSS variables). Fabric compiles them to `@define-color`/`@name`, and GTK takes a named colour from the highest-priority provider that defines it: `config.wallpaper_accent` overrides `@accent` that way, so the accent follows the wallpaper without recompiling SCSS. Between providers GTK goes by priority, not selector specificity.

### Glass and blur

The blur comes from Hyprland layer rules in `~/nixOS/DesktopConfig/modules/home/hyprland/config/hyprland.lua` (NixOS-managed; don't edit `~/.config/hypr`). Each window has its own layer-shell namespace, set through its title (`WaylandWindow(title="fabric-dock")`, or `PopupWindow(namespace=...)`, default `fabric-popup`): `fabric-bar`, `-dock`, `-popup`, `-overview`, `-osd`, `-toast`, `-music` are blurred; `fabric-desktop` and `fabric-corners` aren't (blurring the desktop would turn the clock's soft scrim into a hard-edged frosted shape). A new window needs a namespace and, to be frosted, an entry in that file's `fabric_glass` list. Blur only goes behind pixels above `ignore_alpha = 0.25`, so keep `--bg-glass` above 0.25 and shadows/hover tints below it.

Keep `/* */` comments in the SCSS ASCII-only: a non-ASCII character makes dart-sass emit `@charset "UTF-8"`, which GTK rejects as an unknown @ rule (`//` comments are stripped, so they're fine).

`apply_style` DBus action recompiles and hot-reloads CSS without restarting; Python changes need a restart.

### Utilities (`fabric_config/utils/`)

- `hyprland_monitor.py` — `HyprlandWithMonitors` for multi-monitor awareness; use the shared `get_hyprland_monitors()`
- `icon_resolver.py` — app icon lookup; use the shared `get_icon_resolver()` (instances share one cache file)
- `hyprland_windows.py` — `hyprland_clients()`, `focus_window()`, `close_window()`, `kill_window()` over the shared connection
- `process.py` — `run_command_async(argv, callback(success, stdout, stderr))`
- `app_search.py` — app menu entries, search scoring, launch stats (`~/.cache/fabric/app_launcher/app_stats.json`), calculator, emoji lookup
- `cursors.py` — `install_pointer_cursors()` (called in `main.py`): hand cursor over every `Gtk.Button`/`Switch`/`Scale` app-wide via an enter-notify emission hook (GTK3 ignores CSS `cursor`); other clickable widgets opt in with the `clickable` style class
- `color_picker.py` — `pick_color(delay_ms)`: hyprpicker, copies the hex and notifies
- `uri.py` — `file_uri_to_path()` (decodes `%20` etc.; don't slice `[7:]`)
- `accent.py` — accent color extraction from images
- `snippits/animator.py` — animation utility
- `widgets/sparkline.py` — `Sparkline`, a filled line chart in the widget's CSS `color`

Note: fabric's `exec_shell_command_async` only calls back per **stdout line** and never reads stderr. A command that prints nothing never triggers the callback, and failures go unnoticed. Use `run_command_async` when you need completion or error handling. For long-running chatty processes (e.g. wf-recorder), silence their output rather than piping it unread.

## gi.repository type stubs

Type stubs come from `pygobject-stubs`, pinned to GTK3 (`PYGOBJECT_STUB_CONFIG = "Gtk3,Gdk3"`) in the `flake.nix` overlay. Don't add `ps.pygobject-stubs` in `shell.nix`: that pulls in the unpinned GTK4 build and conflicts. The same override marks the stubs `partial` (so `gi._propertyhelper` etc. resolve to the real `gi`, which Fabric's `Property` needs) and copies in stubs for typelibs it lacks, generated by `nix/gi-extra-stubs.nix`. To stub a new typelib, add it to `modules` there (and its library to `buildInputs`). Don't merge extra stubs in through `python.withPackages`: that turns `gi-stubs/` into a directory of symlinks, which basedpyright then ignores. Stubs for non-gi modules without their own (e.g. the `hyprland_toplevel_streamer` pyo3 extension) live in `typings/`.

basedpyright settings are in `pyproject.toml` (`[tool.basedpyright]`), which makes editors ignore their own `basedpyright.analysis.*` settings, so set the mode there. Under direnv, the shellHook symlinks the dev shell's Python env to `.direnv/python`, a stable path (the store path changes on every rebuild); `pyproject.toml` points basedpyright at it with `venvPath`/`venv`, which overrides whatever interpreter the editor passes (VS Code's Python Environments extension remembers stale ones). It honours `# type: ignore`, and the `Property` getters need return annotations: without one, a getter that returns an attribute its setter assigns makes basedpyright lose the decorator ("Cannot access attribute "setter" for class "FunctionType"").

`gi.require_version(...)` must precede the matching `from gi.repository import ...`; mark those imports `# noqa: E402`.

## Nix notes

- Python version is controlled by `pythonPackagesAttr = "python314Packages"` in `flake.nix` — change this one value to switch Python versions.
- Nix formatter: `nixfmt-rfc-style` (run `nix fmt`).
- The package is built via `derivation.nix`; the `fabric-config` script entrypoint is defined in `pyproject.toml`.
