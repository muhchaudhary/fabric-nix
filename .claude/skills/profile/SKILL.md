---
name: profile
description: This skill should be used when the user asks to "profile the project", "profile startup", "measure startup time", "find slow components", "profile fabric", "check performance", or wants to identify bottlenecks in initialization of this Fabric/GTK4 bar.
version: 0.1.0
---

# Profiling the Fabric Bar

Profile this Python GTK4 status bar to find initialization bottlenecks and slow component construction.

## Two profiling modes

### 1. Full cProfile startup trace

Captures all Python calls from process start until `Application.run()` hands off to the GTK main loop.

```bash
python .claude/skills/profile/scripts/profile_startup.py 2>&1 | less
```

Output goes to **stderr** (so GTK warnings mix in — pipe through `grep -v GLib` if noisy). The app quits automatically after 500ms. A binary `startup.prof` is written to `.claude/skills/profile/` for interactive exploration.

Visualize with snakeviz (install once: `pip install snakeviz`):

```bash
snakeviz .claude/skills/profile/startup.prof
```

Or inspect interactively:

```bash
python -m pstats .claude/skills/profile/startup.prof
# inside pstats: sort cumulative / stats 30
```

### 2. Per-component wall-time timer

Patches each top-level component's `__init__` and prints a sorted table after the process exits. Send DBus quit to stop it: `dbus-send --session --dest=org.Fabric.fabric /org/Fabric/fabric org.Fabric.fabric.Evaluate string:"quit()"`

```bash
python .claude/skills/profile/scripts/component_timer.py 2>&1 | grep -A 30 "Component init"
```

Output looks like:

```
==================================================
Component init times:
==================================================
  StatusBarSeperated             312.4 ms  ######...
  Overview                        88.1 ms  #####
  NotificationPopup               21.3 ms  ####
  AppMenu                         15.0 ms  ###
  SystemOSD                        9.2 ms  ##
  ScreenCorners                    1.1 ms
  TOTAL                          447.1 ms
==================================================
```

## Interpreting cProfile output

Key columns: `cumtime` (total time including callees), `tottime` (time in function itself), `ncalls`.

Look for:

| Pattern | Likely cause |
|---|---|
| High `cumtime` on `__init__` of a widget | Expensive widget tree construction |
| Many calls to `set_stylesheet` / `apply_css` | CSS being re-applied per widget |
| `import` frames in top 10 | Slow Python module import at startup |
| `GLib.idle_add` / `connect` appearing many times | Signal connection overhead |

## What to profile

- **Startup slowness** → use `profile_startup.py`. Focus on `cumtime` for constructors in `fabric_config/components/`.
- **Specific widget slowness** → add `time.monotonic()` brackets around the suspect constructor in `main.py` or `config.py`.
- **Service init** → `config.py` initializes all services at import time. Check if `NetworkClient`, `MprisPlayerManager`, or `brightness` appear high in the cProfile output.
- **CSS load time** → wrap `apply_style()` in `main.py` with a timer; CSS is loaded via `set_stylesheet_from_file`.

## Running inside the devshell

The scripts must run inside the direnv devshell (Python packages are not globally installed):

```bash
# From the project root, inside the nix devshell:
python .claude/skills/profile/scripts/profile_startup.py
```

If running from outside the project directory, use the `direnv_cd` pattern from `readme.md`.

## Adding a timer to any component

To instrument a specific widget without running the full profiler, add wall-time logging directly:

```python
import time
t0 = time.monotonic()
self.some_widget = SomeWidget()
print(f"SomeWidget: {(time.monotonic()-t0)*1000:.1f}ms", file=__import__('sys').stderr)
```

Remove timing code after investigation — do not leave it in production.
