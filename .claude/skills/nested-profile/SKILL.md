---
name: nested-profile
description: This skill should be used when the user asks to profile the bar's steady-state RAM or CPU, find memory leaks, "profile in a nested/headless Hyprland", measure the bar "without the live bar interfering", or run, watch, screenshot or capture fabric in an isolated compositor. Runs the whole bar inside a hidden nested Hyprland that mirrors the real monitors and writes a memory/CPU report.
version: 0.1.0
---

# Profiling fabric in a nested Hyprland

`scripts/nested.py` starts a throwaway Hyprland **inside** the running
session, and `scripts/profile_fabric.py` runs the whole bar in it and
measures it. The live bar, its D-Bus names and its cache are left alone, so
numbers aren't skewed by it (and nothing it does is disturbed).

How it's isolated:

- **Outputs**: one nested output per host monitor (`WAYLAND-1` mirrors the
  leftmost host monitor, `WAYLAND-2` the next, ...) at the same size and layout.
  They are windows of the host compositor, floated on a special workspace that
  is never opened (`special:fabric-nested`), with `render_unfocused`. While it's
  up, the host's `misc.render_unfocused_fps` is raised to 60 so the hidden
  outputs get frame callbacks at a real monitor's rate; `down` restores it.
- **D-Bus**: a private session bus (`dbus-daemon --session`), so fabric's names
  (`org.Fabric.fabric`, notifications, tray watcher) never meet the live bar's.
  System-bus services (NetworkManager, BlueZ, UPower, logind) and PulseAudio
  are the real ones. No MPRIS players or tray items show up on the private bus.
- **Cache**: `XDG_CACHE_HOME` points at a copy of `~/.cache/fabric` (other
  entries are symlinked), so history, launch stats and CSS writes stay out of
  the real cache. Config/data dirs are the real ones (read-mostly).
- **Wallpaper**: hyprpaper inside the nested session, showing what each host
  monitor shows.

Headless outputs (`hyprctl output create headless`) don't work nested on this
NVIDIA machine (GBM can't allocate their buffers), hence hidden Wayland outputs.

## Profile

```bash
python .claude/skills/nested-profile/scripts/profile_fabric.py            # 15 s warmup, 60 s measured
python .claude/skills/nested-profile/scripts/profile_fabric.py --tracemalloc --cprofile
python .claude/skills/nested-profile/scripts/profile_fabric.py --duration 300   # leak hunting
python .claude/skills/nested-profile/scripts/profile_fabric.py \
  --exercise "20:the_app.appMenu.toggle_popup()" \
  --exercise "25:the_app.appMenu.toggle_popup()" --screenshot-at 22 --show
```

It brings the nested session up (and down afterwards, unless it was already
up or `--keep`), runs `fabric_config.main` in it, waits `--warmup` seconds,
then samples for `--duration` seconds and quits. Output goes to
`reports/<timestamp>/`: `report.txt` (printed), `report.json` (all samples),
`fabric.log`, `startup.prof`/`steady.prof` with `--cprofile`, and
`screen-<N>s.png` for each `--screenshot-at`.

| Option | Purpose |
|---|---|
| `--warmup S` / `--duration S` / `--interval S` | timing (defaults 15 / 60 / 1) |
| `--tracemalloc` | Python allocation sites, and what grew during the measured window |
| `--cprofile` | startup (by cumulative) and steady state (by own time). Note cProfile on 3.12+ sees every thread: `time.sleep` in worker threads shows up |
| `--exercise "SECONDS:CODE"` | run CODE in `fabric_config.main`'s namespace (`the_app`, ...) SECONDS after start; repeatable |
| `--screenshot-at SECONDS` | grim the nested screen then; repeatable |
| `--show` | put the nested outputs on screen for the run (see below) |
| `--monitors N` | mirror at most N host monitors |
| `--keep` | leave the nested session running afterwards |

### Reading the report

- **anon / glibc kept**: `RssAnon` is heap memory. "glibc kept" is what
  `malloc_trim(0)` hands back at the end: memory freed but held by glibc's
  arenas (big transient allocations on worker threads cause this).
- **slope**: a linear fit over the samples. A steady positive anon slope over
  a long run with no `--exercise` suggests a leak; check the tracemalloc growth
  list, then native (GTK/cairo) objects.
- **by mapping kind**: `wayland buffers` are the windows' shm buffers (each
  layer surface is w*h*4 bytes, GTK can keep two). `LAYER SURFACES` lists every
  surface fabric has mapped with its size, so a full-screen layer that only
  needs a corner stands out.
- **CPU**: per-thread CPU and wakeups/s (context switches) in the measured
  window. Idle wakeups matter as much as CPU on a laptop.
- **WINDOWS**: widgets per toplevel, including hidden popups built at startup.

## Watch it, screenshot it, run things in it

```bash
N=.claude/skills/nested-profile/scripts/nested.py
python $N up                     # start (prints the state file)
python $N run -- python run_fabric.py &   # anything, inside the nested session
python $N show                   # every nested output 1:1 over the monitor it mirrors
python $N show WAYLAND-1 --monitor DP-1
python $N hide
python $N screenshot [-o out.png] [--output WAYLAND-1]   # grim inside; default screenshots/<ts>.png
eval "$(python $N env)"          # or export the nested env into a shell
python $N status
python $N down                   # stop everything, undo host changes
```

`show` moves the outputs' host windows onto each monitor's current workspace
at the monitor's origin (never resized: that would change the nested
resolution). Mouse and keyboard go to the nested session while it's shown.
The host bar still draws on top of it. `hide` moves them back.

The **capture skill works inside it** unchanged, both modes:

```bash
python $N run -- python .claude/skills/capture/scripts/capture_component.py \
  fabric_config.components.app_menu:AppMenu --screen -o /tmp/am.png
```

## Caveats

- The nested config is minimal: no blur/layer rules, animations or binds, so
  `--screen` captures show the glass without blur.
- `hyprsunset` isn't running inside, so the night light service reports
  unavailable.
- The host window rule (`fabric-nested`) is added at runtime with `hyprctl
  eval`; `down` disables it, and a host config reload removes it.
- Run from the dev shell (direnv), from the project root.
