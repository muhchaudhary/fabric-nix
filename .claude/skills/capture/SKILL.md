---
name: capture
description: This skill should be used when the user asks to "capture", "screenshot", "screengrab", "render" or "preview" a component, popup, widget or window of this Fabric bar, or when visually verifying a UI change (layout, styling, theming) before restarting the bar. Renders the component to a PNG that can then be viewed with the Read tool.
version: 0.1.0
---

# Capturing Fabric components

Render any component of this GTK3 bar to a PNG. Use it to check UI changes
visually: layout, sizing, rounding, theming. It doesn't need a screenshot tool
and doesn't need the running bar restarted.

The script starts the component in its **own short-lived Fabric application**
under a unique name, so it never touches the running bar. It compiles the
project's SCSS for the chosen theme, opens the component, waits for async
content, draws the widget with cairo, writes the PNG and quits.

## Usage

```bash
python .claude/skills/capture/scripts/capture_component.py TARGET [options]
```

Run it from the dev shell (direnv). `TARGET` is `module:attribute`:

- **a class** is instantiated with no arguments (e.g. `...overview:Overview`)
- **an instance** is used as-is (e.g. module-level popups like `...wallpaper_picker:wallpaper_picker`)

How it is opened:

- **`PopupWindow`** subclasses: `toggle_popup()` is called and the revealed content is captured
- **other windows:** `show_all()`, then the window's child is captured
- **bare widgets:** placed in a temporary window

Options:

| Option | Default | Purpose |
|---|---|---|
| `-o, --out PATH` | `.claude/skills/capture/captures/<attribute>-<theme>.png` | output file |
| `--theme dark\|light` | `dark` | which `main*.scss` to compile; background matches |
| `--delay MS` | `2500` | wait before capturing, for thumbnails, previews and network data |
| `--scale N` | `1` | render scale; use `2` for sharp detail |
| `--eval CODE` | — | Python run after opening and before the delay; `obj` is the target, `widget` the captured widget |
| `--transparent` | off | skip the background fill |

Then **view the PNG with the Read tool** to inspect it.

## Known targets

| Component | TARGET |
|---|---|
| Workspace overview | `fabric_config.components.overview:Overview` |
| Wallpaper picker | `fabric_config.components.wallpaper_picker:wallpaper_picker` |
| App launcher | `fabric_config.components.app_menu:AppMenu` |
| Quick settings | `fabric_config.components.quick_settings.quick_settings:QuickSettingsPopup` |
| Prayer times | `fabric_config.components.bar.widgets.prayer_times:PrayerTimesPopup` |
| Clipboard history | `fabric_config.components.bar.widgets.clipboard_history:ClipboardHistoryPopup` |
| Power menu | `fabric_config.components.bar.widgets.power_menu:PowerMenuPopup` |
| Status bar | `fabric_config.components.bar.bar:StatusBarSeperated` |

## Examples

```bash
# overview in both themes
python .claude/skills/capture/scripts/capture_component.py fabric_config.components.overview:Overview
python .claude/skills/capture/scripts/capture_component.py fabric_config.components.overview:Overview --theme light

# crisp wallpaper picker, scrolled down a bit first
python .claude/skills/capture/scripts/capture_component.py \
    fabric_config.components.wallpaper_picker:wallpaper_picker --scale 2 \
    --eval "obj.wallpaper_grid.get_vadjustment().set_value(300)"

# power menu with the confirmation revealed
python .claude/skills/capture/scripts/capture_component.py \
    fabric_config.components.bar.widgets.power_menu:PowerMenuPopup \
    --eval "obj.confirm_menu.set_reveal_child(True)"
```

## Caveats

- **Importing a component runs its side effects.** The wallpaper picker re-applies the last wallpaper, the overview captures live window frames, and clipboard/prayer services start. Nothing destructive, but be aware of it.
- **Don't send compositor commands** (e.g. via `--eval`) as part of a capture. Hyprland window dispatchers without an explicit `window` act on the *focused* window.
- **Async content needs time.** If thumbnails or previews are missing, raise `--delay`.
- **"widget has no size" errors** usually mean the component didn't open. Check the target or open it via `--eval`.
- **Python changes show up immediately** because the capture imports the working tree. The running bar still needs a restart.
- **Captures land in `captures/`**, which is gitignored.
