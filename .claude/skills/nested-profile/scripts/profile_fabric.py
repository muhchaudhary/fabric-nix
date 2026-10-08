#!/usr/bin/env python3
"""
Run the whole bar inside the nested Hyprland (nested.py) and profile it:
startup time, memory (RSS by kind, by mapping, Wayland buffers per layer,
memory glibc keeps after frees), CPU per thread, wakeups, and optionally
Python allocations (tracemalloc, with growth over the run) and a cProfile
of the steady state.

    profile_fabric.py [--duration S] [--warmup S] [--tracemalloc] [--cprofile]
                      [--exercise "SECONDS:CODE" ...] [--keep]
                      [--show] [--screenshot-at SECONDS ...]

Writes reports/<timestamp>/{report.txt,report.json,fabric.log,*.prof} next to
this skill and prints report.txt.
"""

import argparse
import ctypes
import datetime
import gc
import json
import os
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
PROJECT = SKILL.parent.parent.parent
REPORTS = SKILL / "reports"
CHILD_FLAG = "FABRIC_NESTED_PROFILE_CHILD"
TICK = os.sysconf("SC_CLK_TCK")
PAGE_KB = os.sysconf("SC_PAGE_SIZE") // 1024


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--duration", type=float, default=60, help="measured seconds (default 60)"
    )
    p.add_argument(
        "--warmup", type=float, default=15, help="seconds before measuring (default 15)"
    )
    p.add_argument(
        "--interval", type=float, default=1, help="sample period (default 1 s)"
    )
    p.add_argument(
        "--tracemalloc", action="store_true", help="track Python allocations (slower)"
    )
    p.add_argument(
        "--cprofile", action="store_true", help="cProfile startup and the steady state"
    )
    p.add_argument(
        "--exercise",
        action="append",
        default=[],
        metavar="SECONDS:CODE",
        help="run CODE (in fabric_config.main's namespace, e.g. "
        "'the_app.appMenu.toggle_popup()') SECONDS after startup; repeatable",
    )
    p.add_argument("--monitors", type=int, default=99, help="mirror at most N monitors")
    p.add_argument(
        "--keep", action="store_true", help="leave the nested session running"
    )
    p.add_argument(
        "--show", action="store_true", help="watch the run live on your monitors"
    )
    p.add_argument(
        "--screenshot-at",
        type=float,
        action="append",
        default=[],
        metavar="SECONDS",
        help="grab the nested screen SECONDS after fabric starts; repeatable",
    )
    p.add_argument("--out", type=Path, help="report directory")
    return p.parse_args()


# Launcher: outside the nested session


def launch(args) -> int:
    sys.path.insert(0, str(HERE))
    import nested  # noqa: E402

    out = args.out or REPORTS / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    started_here = nested.load_state() is None
    state = nested.up(argparse.Namespace(monitors=args.monitors, fps=60))
    env = nested.nested_env(state)
    env[CHILD_FLAG] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONFAULTHANDLER"] = "1"
    argv = [
        sys.executable,
        str(Path(__file__).resolve()),
        *sys.argv[1:],
        "--out",
        str(out),
    ]
    timeout = args.warmup + args.duration + 120
    timers = [
        threading.Timer(
            at,
            lambda at=at: nested.screenshot(state, out / f"screen-{at:g}s.png"),
        )
        for at in args.screenshot_at
    ]
    code = None
    if args.show:
        nested.show(state, None, None)
    try:
        with open(out / "fabric.log", "w") as log:
            proc = subprocess.Popen(argv, env=env, cwd=PROJECT, stdout=log, stderr=log)
            state["fabric_pid"] = proc.pid
            nested.STATE_FILE.write_text(json.dumps(state, indent=2))
            for timer in timers:
                timer.start()
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                code = -1
                print(
                    f"[profile] fabric didn't finish in {timeout:.0f} s",
                    file=sys.stderr,
                )
    finally:
        for timer in timers:
            timer.cancel()
        if args.show:
            nested.hide(state)
        if started_here and not args.keep:
            nested.down()
    report = out / "report.txt"
    if report.exists():
        print(report.read_text())
        print(f"[profile] report: {out}", file=sys.stderr)
    else:
        print(
            f"[profile] no report (exit {code}); see {out / 'fabric.log'}",
            file=sys.stderr,
        )
    return 0 if report.exists() else 1


# Child: fabric itself, inside the nested session


def status() -> dict[str, int]:
    fields = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in ("VmRSS", "RssAnon", "RssFile", "RssShmem", "VmSwap", "Threads"):
            fields[key] = int(value.split()[0])
    return fields


def thread_ticks() -> dict[str, dict]:
    threads = {}
    for task in Path("/proc/self/task").iterdir():
        try:
            stat = (task / "stat").read_text()
            comm = (task / "comm").read_text().strip()
            st = (task / "status").read_text()
        except OSError:
            continue
        fields = stat[stat.rindex(")") + 2 :].split()
        ctx = sum(
            int(line.split()[1])
            for line in st.splitlines()
            if line.startswith(
                ("voluntary_ctxt_switches", "nonvoluntary_ctxt_switches")
            )
        )
        threads[task.name] = {
            "comm": comm,
            "ticks": int(fields[11]) + int(fields[12]),
            "ctx": ctx,
        }
    return threads


def smaps_breakdown() -> dict:
    by_name: dict[str, int] = defaultdict(int)
    buffers = []
    current = None
    size_kb = 0
    for line in Path("/proc/self/smaps").read_text().splitlines():
        head = line.split()
        if "-" in head[0] and len(head) >= 5 and ":" in head[3]:
            start, end = (int(x, 16) for x in head[0].split("-"))
            size_kb = (end - start) // 1024
            current = head[5] if len(head) > 5 else "[anon]"
        elif head[0] == "Rss:" and current is not None:
            rss = int(head[1])
            by_name[current] += rss
            if "gdk-wayland" in current and size_kb > 64:
                buffers.append({"size_kb": size_kb, "rss_kb": rss})
    groups: dict[str, int] = defaultdict(int)
    for name, rss in by_name.items():
        if name in ("[anon]", "[heap]", "[stack]"):
            groups[name] += rss
        elif "memfd:gdk-wayland" in name:
            groups["wayland buffers (memfd:gdk-wayland)"] += rss
        elif name.startswith("/memfd:") or name.startswith("/dev/"):
            groups[name.split(" ")[0]] += rss
        elif "/fonts/" in name:
            groups["fonts"] += rss
        elif ".so" in name:
            groups["shared libraries"] += rss
        else:
            groups["other files"] += rss
    top_files = sorted(
        ((rss, name) for name, rss in by_name.items() if name.startswith("/")),
        reverse=True,
    )[:15]
    return {
        "groups_kb": dict(sorted(groups.items(), key=lambda kv: -kv[1])),
        "top_mappings_kb": [{"name": n, "rss_kb": r} for r, n in top_files],
        "wayland_buffers": sorted(buffers, key=lambda b: -b["size_kb"]),
    }


def nested_layers() -> list[dict]:
    try:
        out = subprocess.run(
            ["hyprctl", "-j", "layers"], capture_output=True, text=True, timeout=5
        ).stdout
        data = json.loads(out)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
    layers = []
    for monitor, info in data.items():
        for level, entries in info.get("levels", {}).items():
            for layer in entries:
                if layer.get("pid") == os.getpid():
                    w, h = layer["w"], layer["h"]
                    layers.append(
                        {
                            "monitor": monitor,
                            "level": int(level),
                            "namespace": layer["namespace"],
                            "w": w,
                            "h": h,
                            "buffer_kb": w * h * 4 // 1024,
                        }
                    )
    return sorted(layers, key=lambda layer: -layer["buffer_kb"])


def widget_counts() -> list[dict]:
    from gi.repository import Gtk

    def count(widget) -> int:
        n = 1
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children():
                n += count(child)
        return n

    return sorted(
        (
            {
                "title": w.get_title() or type(w).__name__,
                "class": type(w).__name__,
                "visible": w.get_visible(),
                "widgets": count(w),
            }
            for w in Gtk.Window.list_toplevels()
        ),
        key=lambda d: -d["widgets"],
    )


def slope_kb_per_min(samples: list[dict], key: str) -> float:
    if len(samples) < 3:
        return 0.0
    xs = [s["t"] for s in samples]
    ys = [s[key] for s in samples]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    var = sum((x - mx) ** 2 for x in xs)
    return 60 * sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var if var else 0.0


def child(args) -> int:
    t_start = time.monotonic()
    tracer = None
    if args.tracemalloc:
        import tracemalloc

        tracemalloc.start(1)
        tracer = tracemalloc
    startup_prof = None
    if args.cprofile:
        import cProfile

        startup_prof = cProfile.Profile()
        startup_prof.enable()

    sys.path.insert(0, str(PROJECT))
    import fabric_config.main as fabric_main
    from gi.repository import GLib

    if startup_prof is not None:
        startup_prof.disable()
        startup_prof.dump_stats(str(args.out / "startup.prof"))
    startup_ms = (time.monotonic() - t_start) * 1000
    after_startup = status()
    ns = vars(fabric_main)

    for spec in args.exercise:
        seconds, _, code = spec.partition(":")

        def run(code=code):
            try:
                exec(code, ns)
            except Exception as e:
                print(f"[profile] exercise {code!r} failed: {e!r}", file=sys.stderr)
            return False

        GLib.timeout_add(int(float(seconds) * 1000), run)

    samples: list[dict] = []
    marks: dict = {}

    def sample():
        now = time.monotonic()
        st = status()
        samples.append(
            {
                "t": now - marks["t0"],
                "rss": st["VmRSS"],
                "anon": st["RssAnon"],
                "shmem": st["RssShmem"],
                "file": st["RssFile"],
                "threads": st["Threads"],
            }
        )
        return True

    def begin():
        marks["t0"] = time.monotonic()
        marks["threads"] = thread_ticks()
        marks["status"] = status()
        if tracer is not None:
            gc.collect()
            marks["snap"] = tracer.take_snapshot()
        if args.cprofile:
            import cProfile

            marks["prof"] = cProfile.Profile()
            marks["prof"].enable()
        sample()
        marks["timer"] = GLib.timeout_add(int(args.interval * 1000), sample)
        GLib.timeout_add(int(args.duration * 1000), finish)
        return False

    def finish():
        GLib.source_remove(marks["timer"])
        sample()
        if "prof" in marks:
            marks["prof"].disable()
            marks["prof"].dump_stats(str(args.out / "steady.prof"))
        elapsed = time.monotonic() - marks["t0"]
        try:
            report = build_report(
                args, startup_ms, after_startup, samples, marks, elapsed, tracer
            )
            write_report(args.out, report)
        except Exception:
            import traceback

            traceback.print_exc()
        fabric_main.the_app.quit()
        return False

    GLib.timeout_add(int(args.warmup * 1000), begin)
    fabric_main.main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


def build_report(
    args, startup_ms, after_startup, samples, marks, elapsed, tracer
) -> dict:
    end_threads = thread_ticks()
    threads = []
    for tid, end in end_threads.items():
        begin = marks["threads"].get(tid, {"ticks": 0, "ctx": 0})
        threads.append(
            {
                "tid": tid,
                "comm": end["comm"],
                "cpu_pct": 100 * (end["ticks"] - begin["ticks"]) / TICK / elapsed,
                "wakeups_per_s": (end["ctx"] - begin["ctx"]) / elapsed,
            }
        )
    threads.sort(key=lambda t: -t["cpu_pct"])
    total_cpu = sum(t["cpu_pct"] for t in threads)

    smaps = smaps_breakdown()
    layers = nested_layers()
    widgets = widget_counts()

    py = {}
    if tracer is not None:
        gc.collect()
        snap = tracer.take_snapshot()
        py["traced_mb"] = tracer.get_traced_memory()[0] / 1e6
        py["top_lines"] = [
            {"where": str(s.traceback[0]), "kb": s.size // 1024, "count": s.count}
            for s in snap.statistics("lineno")[:25]
        ]
        py["growth"] = [
            {
                "where": str(s.traceback[0]),
                "kb": s.size_diff // 1024,
                "count": s.count_diff,
            }
            for s in snap.compare_to(marks["snap"], "lineno")[:20]
            if s.size_diff > 0
        ]
    objects = gc.get_objects()
    py["gc_objects"] = len(objects)
    py["top_types"] = Counter(type(o).__name__ for o in objects).most_common(20)
    del objects

    # memory glibc holds after frees: what malloc_trim gives back
    before = status()["RssAnon"]
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
        trimmed_kb = before - status()["RssAnon"]
    except OSError:
        trimmed_kb = None

    anon = [s["anon"] for s in samples]
    rss = [s["rss"] for s in samples]
    return {
        "config": {
            "duration_s": args.duration,
            "warmup_s": args.warmup,
            "exercise": args.exercise,
            "tracemalloc": args.tracemalloc,
            "cprofile": args.cprofile,
        },
        "startup": {"import_and_construct_ms": startup_ms, "status_kb": after_startup},
        "memory": {
            "rss_kb": {
                "start": rss[0],
                "end": rss[-1],
                "min": min(rss),
                "max": max(rss),
            },
            "anon_kb": {
                "start": anon[0],
                "end": anon[-1],
                "min": min(anon),
                "max": max(anon),
            },
            "shmem_kb_end": samples[-1]["shmem"],
            "file_kb_end": samples[-1]["file"],
            "anon_slope_kb_per_min": slope_kb_per_min(samples, "anon"),
            "rss_slope_kb_per_min": slope_kb_per_min(samples, "rss"),
            "malloc_trim_freed_kb": trimmed_kb,
            "smaps": smaps,
            "fds": len(os.listdir("/proc/self/fd")),
        },
        "cpu": {"total_pct": total_cpu, "threads": threads},
        "layers": layers,
        "windows": widgets,
        "python": py,
        "samples": samples,
    }


def fmt_kb(kb: float | None) -> str:
    if kb is None:
        return "n/a"
    return f"{kb / 1024:7.1f} MB"


def write_report(out: Path, r: dict):
    (out / "report.json").write_text(json.dumps(r, indent=2, default=str))
    m, c = r["memory"], r["cpu"]
    lines = [
        "=" * 64,
        f"fabric, nested: {r['config']['duration_s']:.0f} s measured "
        f"after {r['config']['warmup_s']:.0f} s warmup",
        "=" * 64,
        f"startup (import + construct): {r['startup']['import_and_construct_ms']:.0f} ms",
        "",
        "MEMORY (kB from /proc/self/status)",
        f"  RSS    start {fmt_kb(m['rss_kb']['start'])}  end {fmt_kb(m['rss_kb']['end'])}"
        f"  max {fmt_kb(m['rss_kb']['max'])}  slope {m['rss_slope_kb_per_min']:+.0f} kB/min",
        f"  anon   start {fmt_kb(m['anon_kb']['start'])}  end {fmt_kb(m['anon_kb']['end'])}"
        f"  max {fmt_kb(m['anon_kb']['max'])}  slope {m['anon_slope_kb_per_min']:+.0f} kB/min",
        f"  shmem  {fmt_kb(m['shmem_kb_end'])}   file-backed {fmt_kb(m['file_kb_end'])}"
        f"   fds {m['fds']}",
        f"  glibc kept (freed by malloc_trim at the end): {fmt_kb(m['malloc_trim_freed_kb'])}",
        "",
        "  by mapping kind:",
        *(
            f"    {fmt_kb(kb)}  {name}"
            for name, kb in list(m["smaps"]["groups_kb"].items())[:10]
        ),
        "  top file mappings:",
        *(
            f"    {fmt_kb(e['rss_kb'])}  {e['name'].split('/')[-1]}"
            for e in m["smaps"]["top_mappings_kb"][:8]
        ),
        "",
        "LAYER SURFACES (one ARGB buffer each = w*h*4; GTK may hold two)",
        *(
            f"    {fmt_kb(layer['buffer_kb'])}  {layer['namespace']:18s} "
            f"{layer['w']}x{layer['h']} on {layer['monitor']} (level {layer['level']})"
            for layer in r["layers"]
        ),
        f"  wayland buffers mapped: {len(m['smaps']['wayland_buffers'])}, "
        f"{fmt_kb(sum(b['rss_kb'] for b in m['smaps']['wayland_buffers']))}",
        "",
        f"CPU  total {c['total_pct']:.2f}%",
        *(
            f"    {t['cpu_pct']:6.2f}%  {t['wakeups_per_s']:7.1f} wakeups/s  {t['comm']}"
            for t in c["threads"]
            if t["cpu_pct"] > 0.005 or t["wakeups_per_s"] > 0.5
        ),
        "",
        "WINDOWS (widgets per toplevel)",
        *(
            f"    {w['widgets']:5d}  {w['title']} ({w['class']}{', shown' if w['visible'] else ''})"
            for w in r["windows"]
        ),
        f"  total widgets: {sum(w['widgets'] for w in r['windows'])}",
        "",
        "PYTHON",
        f"  gc objects: {r['python']['gc_objects']}",
        "  " + ", ".join(f"{name} {n}" for name, n in r["python"]["top_types"][:10]),
    ]
    py = r["python"]
    if "traced_mb" in py:
        lines += [
            f"  traced: {py['traced_mb']:.1f} MB",
            "  top allocation sites:",
            *(
                f"    {e['kb']:7d} kB {e['count']:7d}x  {e['where']}"
                for e in py["top_lines"][:15]
            ),
            "  grew during the measured window:",
            *(
                f"    {e['kb']:+7d} kB {e['count']:+7d}x  {e['where']}"
                for e in py["growth"][:10]
            ),
        ]
    if r["config"]["cprofile"]:
        import pstats
        import io

        # startup by cumulative (which constructors), steady state by own time
        for name, order in (("startup", "cumulative"), ("steady", "tottime")):
            lines.append(f"\ncProfile {name} (top 20 by {order}):")
            buf = io.StringIO()
            try:
                pstats.Stats(str(out / f"{name}.prof"), stream=buf).sort_stats(
                    order
                ).print_stats(20)
                lines.append(buf.getvalue())
            except OSError:
                lines.append(f"  (missing {name}.prof)")
    (out / "report.txt").write_text("\n".join(lines) + "\n")


def main():
    args = parse_args()
    if os.environ.get(CHILD_FLAG):
        sys.exit(child(args))
    sys.exit(launch(args))


if __name__ == "__main__":
    main()
