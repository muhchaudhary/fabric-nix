#!/usr/bin/env python3
"""
A throwaway Hyprland nested inside the running session, for profiling fabric
without touching the live bar.

The nested compositor runs its outputs as windows of the host Hyprland. A
runtime host window rule floats them on a hidden special workspace at the
real monitors' sizes and keeps them rendering (`render_unfocused`), and the
host's `misc.render_unfocused_fps` is raised to 60 while it runs, so frame
pacing matches a real monitor. Inside it: hyprpaper with the host's current
wallpapers, a private D-Bus session bus (fabric's bus names never meet the
live bar's) and a copy of ~/.cache/fabric (so history, stats and CSS writes
stay out of the real cache).

    nested.py up [--monitors N] [--fps N]     start; prints the state file
    nested.py env                             `export ...` lines for the nested session
    nested.py run -- CMD...                   run CMD inside it
    nested.py show [WAYLAND-N...] [--monitor M]  watch it live (1:1 over the host monitor)
    nested.py hide
    nested.py screenshot [-o PNG] [--output WAYLAND-N]
    nested.py status
    nested.py down                            stop it and undo the host changes
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
STATE_DIR = RUNTIME / "fabric-nested"
STATE_FILE = STATE_DIR / "state.json"
RULE_NAME = "fabric-nested"
SPECIAL = "special:fabric-nested"
DEFAULT_UNFOCUSED_FPS = 15


def log(msg: str):
    print(f"[nested] {msg}", file=sys.stderr, flush=True)


def host_env() -> dict[str, str]:
    env = dict(os.environ)
    if "HYPRLAND_INSTANCE_SIGNATURE" not in env:
        sys.exit(
            "[nested] not inside a Hyprland session (no HYPRLAND_INSTANCE_SIGNATURE)"
        )
    return env


def hyprctl(*args: str, env: dict[str, str] | None = None, json_out=False):
    cmd = ["hyprctl", *(["-j"] if json_out else []), *args]
    out = subprocess.run(cmd, env=env or host_env(), capture_output=True, text=True)
    if json_out:
        return json.loads(out.stdout or "null")
    return out.stdout.strip()


def find_binary(name: str, proc_name: str) -> str:
    """A binary on PATH, else the one the host session is running."""
    if path := shutil.which(name):
        return path
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            if Path(f"/proc/{pid}/comm").read_text().strip() == proc_name:
                return os.readlink(f"/proc/{pid}/exe")
        except OSError:
            continue
    sys.exit(f"[nested] can't find {name}")


def hyprland_binary() -> str:
    # /run/wrappers' Hyprland is a setcap wrapper; use the real one
    start = shutil.which("start-hyprland")
    if start:
        real = Path(start).resolve().parent / "Hyprland"
        if real.exists():
            return str(real)
    return find_binary("Hyprland", ".Hyprland-wrapp")


def wait_for(predicate, timeout: float, what: str):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if (value := predicate()) is not None:
            return value
        time.sleep(0.1)
    raise TimeoutError(f"timed out waiting for {what}")


def load_state() -> dict | None:
    try:
        state = json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return None
    try:
        os.kill(state["hyprland_pid"], 0)
    except OSError:
        return None
    return state


def nested_env(state: dict) -> dict[str, str]:
    env = dict(os.environ)
    env.update(state["env"])
    return env


def host_monitors() -> list[dict]:
    monitors = hyprctl("monitors", json_out=True) or []
    return sorted(
        (m for m in monitors if not m.get("disabled") and "HEADLESS" not in m["name"]),
        key=lambda m: (m["x"], m["y"]),
    )


def host_wallpapers() -> dict[str, str]:
    out = hyprctl("hyprpaper", "listactive")
    walls = {}
    for line in out.splitlines():
        name, sep, path = line.partition(":")
        if sep and path.strip():
            walls[name.strip()] = path.strip()
    return walls


def make_cache(base: Path) -> Path:
    """~/.cache with every entry symlinked, except fabric's, which is copied."""
    real = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    cache = base / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    for entry in real.iterdir():
        target = cache / entry.name
        if entry.name == "fabric":
            shutil.copytree(entry, target, symlinks=True, dirs_exist_ok=True)
        elif not target.exists():
            target.symlink_to(entry)
    return cache


def up(args) -> dict:
    if state := load_state():
        log(f"already running (Hyprland pid {state['hyprland_pid']})")
        return state
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    for stale in STATE_DIR.iterdir():
        if stale.is_dir():
            shutil.rmtree(stale, ignore_errors=True)
        else:
            stale.unlink()

    monitors = host_monitors()[: args.monitors] or [
        {"name": "fallback", "width": 1920, "height": 1080, "x": 0, "y": 0}
    ]
    walls = host_wallpapers()
    log(
        "monitors: "
        + ", ".join(f"{m['name']} {m['width']}x{m['height']}" for m in monitors)
    )

    # host side: hide the nested outputs, keep them rendering at full rate
    first = monitors[0]
    hyprctl(
        "eval",
        "hl.window_rule({ "
        f'name = "{RULE_NAME}", match = {{ class = "^aquamarine$" }}, '
        f'workspace = "{SPECIAL} silent", float = true, '
        f'size = "{first["width"]} {first["height"]}", '
        "render_unfocused = true, no_initial_focus = true })",
    )
    old_fps = (
        hyprctl("getoption", "misc:render_unfocused_fps", json_out=True) or {}
    ).get("int", DEFAULT_UNFOCUSED_FPS)
    hyprctl("eval", f"hl.config({{ misc = {{ render_unfocused_fps = {args.fps} }} }})")

    # nested config: its outputs are WAYLAND-1..N, laid out like the host's
    names = [f"WAYLAND-{i + 1}" for i in range(len(monitors))]
    origin_x, origin_y = monitors[0]["x"], monitors[0]["y"]
    lines = [
        f'hl.monitor({{ output = "{name}", mode = "{m["width"]}x{m["height"]}", '
        f'position = "{m["x"] - origin_x}x{m["y"] - origin_y}", scale = 1 }})'
        for name, m in zip(names, monitors)
    ]
    lines.append(
        "hl.config({ misc = { disable_hyprland_logo = true, disable_splash_rendering = true } })"
    )
    config = STATE_DIR / "hyprland.lua"
    config.write_text("\n".join(lines) + "\n")

    env = host_env()
    env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
    hypr_log = open(STATE_DIR / "hyprland.out", "w")
    hypr = subprocess.Popen(
        # through start-hyprland's watchdog, as a session would (Hyprland
        # otherwise warns on screen that it was started without it)
        [
            *(
                [start, "--path", hyprland_binary(), "--"]
                if (start := shutil.which("start-hyprland"))
                else [hyprland_binary()]
            ),
            "--config",
            str(config),
        ],
        env=env,
        stdout=hypr_log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    def find_instance():
        for lock in (RUNTIME / "hypr").glob("*/hyprland.lock"):
            try:
                pid, socket = lock.read_text().split()[:2]
            except (OSError, ValueError):
                continue
            try:
                ours = os.getpgid(int(pid)) == hypr.pid
            except OSError:
                continue
            if ours:
                return int(pid), lock.parent.name, socket
        return None

    try:
        compositor_pid, signature, wayland_socket = wait_for(
            find_instance, 15, "the nested Hyprland"
        )
    except TimeoutError:
        os.killpg(hypr.pid, signal.SIGKILL)  # Hyprland ignores SIGTERM
        undo_host(old_fps)
        sys.exit(f"[nested] Hyprland didn't start; see {STATE_DIR / 'hyprland.out'}")
    nenv = {
        "HYPRLAND_INSTANCE_SIGNATURE": signature,
        "WAYLAND_DISPLAY": wayland_socket,
        "GDK_BACKEND": "wayland",
    }
    state = {
        # the compositor; its process group (start-hyprland's pid) holds the rest
        "hyprland_pid": compositor_pid,
        "pgid": hypr.pid,
        "old_unfocused_fps": old_fps,
        "monitors": {n: m["name"] for n, m in zip(names, monitors)},
        "env": nenv,
        "dir": str(STATE_DIR),
    }
    STATE_FILE.write_text(json.dumps(state, indent=2))
    try:
        _populate(state, compositor_pid, env, names, monitors, walls)
    except BaseException:
        log("setup failed; tearing down")
        down()
        raise
    STATE_FILE.write_text(json.dumps(state, indent=2))
    log(f"up: {signature} on {wayland_socket}; state in {STATE_FILE}")
    return state


def _populate(
    state: dict,
    hypr_pid: int,
    env: dict[str, str],
    names: list[str],
    monitors: list[dict],
    walls: dict[str, str],
):
    """Size the nested outputs, then start its bus and hyprpaper."""
    nenv = state["env"]
    inner = dict(env, **nenv)

    def nested_monitors():
        return hyprctl("monitors", env=inner, json_out=True) or []

    # outputs past the first are new windows on the host: size them exactly
    for name, m in list(zip(names, monitors))[1:]:
        hyprctl("output", "create", "wayland", env=inner)
        address = wait_for(
            lambda: next(
                (
                    c["address"]
                    for c in hyprctl("clients", json_out=True) or []
                    if c["pid"] == hypr_pid and c["title"].endswith(name)
                ),
                None,
            ),
            10,
            f"host window for {name}",
        )
        hyprctl(
            "dispatch",
            f"hl.dsp.window.resize({{ window = 'address:{address}', "
            f"x = {m['width']}, y = {m['height']}, exact = true }})",
        )
    wait_for(
        lambda: (
            True
            if [(o["width"], o["height"]) for o in nested_monitors()]
            == [(m["width"], m["height"]) for m in monitors]
            else None
        ),
        10,
        "nested outputs at the right size",
    )

    # private session bus
    bus = subprocess.run(
        ["dbus-daemon", "--session", "--fork", "--print-address=1", "--print-pid=1"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    nenv["DBUS_SESSION_BUS_ADDRESS"], state["dbus_pid"] = bus[0], int(bus[1])
    STATE_FILE.write_text(json.dumps(state, indent=2))
    nenv["XDG_CACHE_HOME"] = str(make_cache(STATE_DIR))
    inner = dict(env, **nenv)

    # hyprpaper with the host's wallpapers, monitor by monitor
    paper_conf = STATE_DIR / "hyprpaper.conf"
    paper_conf.write_text("ipc = on\nsplash = false\n")
    paper = subprocess.Popen(
        [find_binary("hyprpaper", "hyprpaper"), "-c", str(paper_conf)],
        env=inner,
        stdout=open(STATE_DIR / "hyprpaper.out", "w"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    state["hyprpaper_pid"] = paper.pid
    STATE_FILE.write_text(json.dumps(state, indent=2))
    fallback = next(iter(walls.values()), None)
    wait_for(
        lambda: (
            True
            if (
                RUNTIME
                / "hypr"
                / nenv["HYPRLAND_INSTANCE_SIGNATURE"]
                / ".hyprpaper.sock"
            ).exists()
            else None
        ),
        10,
        "hyprpaper",
    )
    for name, m in zip(names, monitors):
        if wall := walls.get(m["name"], fallback):
            hyprctl("hyprpaper", "wallpaper", f"{name},{wall}", env=inner)


def undo_host(old_fps: int):
    hyprctl("eval", f"hl.config({{ misc = {{ render_unfocused_fps = {old_fps} }} }})")
    # a rule can't be removed at runtime; disable it until the next reload
    hyprctl(
        "eval",
        f'hl.window_rule({{ name = "{RULE_NAME}", enabled = false, '
        'match = { class = "^aquamarine$" } })',
    )


def down(_args=None):
    try:
        state = json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        log("not running")
        return
    for key in ("fabric_pid", "hyprpaper_pid", "dbus_pid"):
        if pid := state.get(key):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    # Hyprland ignores SIGTERM: ask it to exit, then make sure. It was started
    # in its own session, so its process group takes whatever is left
    pid = state["hyprland_pid"]
    hyprctl("dispatch", "hl.dsp.exit()", env=nested_env(state))
    try:
        wait_for(
            lambda: None if Path(f"/proc/{pid}").exists() else True,
            5,
            "Hyprland to exit",
        )
    except TimeoutError:
        pass
    try:
        os.killpg(state.get("pgid", pid), signal.SIGKILL)
    except OSError:
        pass
    signature = state["env"].get("HYPRLAND_INSTANCE_SIGNATURE")
    if signature:
        shutil.rmtree(RUNTIME / "hypr" / signature, ignore_errors=True)
    undo_host(state.get("old_unfocused_fps", DEFAULT_UNFOCUSED_FPS))
    STATE_FILE.unlink(missing_ok=True)
    log("down")


def host_windows(state: dict) -> dict[str, str]:
    """Nested output name -> address of its window on the host."""
    pid = state["hyprland_pid"]
    windows = {}
    for client in hyprctl("clients", json_out=True) or []:
        if client["pid"] == pid and client["class"] == "aquamarine":
            windows[client["title"].rsplit(" ", 1)[-1]] = client["address"]
    return windows


def show(state: dict, outputs: list[str] | None, monitor: str | None):
    """
    Put nested outputs on screen, 1:1 over the host monitor each one mirrors
    (or `monitor`), on that monitor's current workspace. The host bar and
    other layers still draw on top. Windows only move: resizing one would
    change the nested monitor's resolution.
    """
    host = {m["name"]: m for m in hyprctl("monitors", json_out=True) or []}
    windows = host_windows(state)
    for output in outputs or list(state["monitors"]):
        address = windows.get(output)
        target = host.get(monitor or state["monitors"].get(output, ""))
        if address is None or target is None:
            log(
                f"can't show {output} (window {address}, monitor {target and target['name']})"
            )
            continue
        window = f"window = 'address:{address}'"
        hyprctl(
            "dispatch",
            f"hl.dsp.window.move({{ workspace = {target['activeWorkspace']['id']}, "
            f"follow = false, {window} }})",
        )
        hyprctl(
            "dispatch",
            f"hl.dsp.window.move({{ {window}, x = {target['x']}, y = {target['y']}, "
            "exact = true })",
        )
        hyprctl("dispatch", f"hl.dsp.window.bring_to_top({{ {window} }})")
        log(f"showing {output} on {target['name']}")


def hide(state: dict):
    # moved, never toggled: a special workspace that is never opened stays
    # hidden however focus moves
    for address in host_windows(state).values():
        hyprctl(
            "dispatch",
            f"hl.dsp.window.move({{ workspace = '{SPECIAL}', follow = false, "
            f"window = 'address:{address}' }})",
        )


def find_grim() -> str:
    if grim := shutil.which("grim"):
        return grim
    out = subprocess.run(
        ["nix", "build", "--no-link", "--print-out-paths", "nixpkgs#grim"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return os.path.join(out, "bin", "grim")


def screenshot(state: dict, path: Path, output: str | None = None) -> Path:
    """grim inside the nested session: all outputs, or one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    argv = [find_grim(), *(["-o", output] if output else []), str(path)]
    subprocess.run(argv, env=nested_env(state), check=True)
    return path


def require_state() -> dict:
    state = load_state()
    if state is None:
        sys.exit("[nested] not running; start it with `nested.py up`")
    return state


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_up = sub.add_parser("up")
    p_up.add_argument(
        "--monitors", type=int, default=99, help="mirror at most N host monitors"
    )
    p_up.add_argument(
        "--fps", type=int, default=60, help="frame rate of the hidden outputs"
    )
    sub.add_parser("env")
    sub.add_parser("status")
    sub.add_parser("down")
    p_show = sub.add_parser("show", help="put nested outputs on screen")
    p_show.add_argument("outputs", nargs="*", help="WAYLAND-N (default: all)")
    p_show.add_argument("--monitor", help="host monitor to show on")
    sub.add_parser("hide", help="hide the nested outputs again")
    p_shot = sub.add_parser("screenshot", help="grim inside the nested session")
    p_shot.add_argument("-o", "--out", type=Path, help="PNG path")
    p_shot.add_argument("--output", help="only this nested output (WAYLAND-N)")
    p_run = sub.add_parser("run")
    p_run.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    if args.cmd == "up":
        up(args)
    elif args.cmd == "down":
        down()
    elif args.cmd == "env":
        for key, value in require_state()["env"].items():
            print(f"export {key}={value!r}")
    elif args.cmd == "status":
        state = load_state()
        print(json.dumps(state, indent=2) if state else "not running")
    elif args.cmd == "show":
        show(require_state(), args.outputs, args.monitor)
    elif args.cmd == "hide":
        hide(require_state())
    elif args.cmd == "screenshot":
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out = (
            args.out
            or Path(__file__).resolve().parent.parent / "screenshots" / f"{stamp}.png"
        )
        print(screenshot(require_state(), out, args.output))
    elif args.cmd == "run":
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        sys.exit(subprocess.call(command, env=nested_env(require_state())))


if __name__ == "__main__":
    main()
