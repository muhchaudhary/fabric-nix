#!/usr/bin/env python3
"""Profile fabric startup — captures cProfile data up to GTK main loop entry."""

import cProfile
import pstats
import io
import sys
import os
import time

# Patch Application.run to stop profiling at GTK loop entry
_profile = cProfile.Profile()
_start_wall = time.monotonic()
_profile.enable()

# Monkey-patch to capture the moment run() is called
import fabric  # noqa: E402

_original_run = None


def _patched_run(self, *args, **kwargs):
    _profile.disable()
    wall_elapsed = time.monotonic() - _start_wall

    output = io.StringIO()
    stats = pstats.Stats(_profile, stream=output)
    stats.sort_stats("cumulative")

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"Startup wall time: {wall_elapsed * 1000:.1f} ms", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    # Print top 40 cumulative-time functions
    stats.print_stats(40)
    print(output.getvalue(), file=sys.stderr)

    # Dump .prof file for use with snakeviz / pyprof2calltree
    prof_path = os.path.join(os.path.dirname(__file__), "..", "startup.prof")
    _profile.dump_stats(os.path.abspath(prof_path))
    print(f"Profile saved to: {os.path.abspath(prof_path)}", file=sys.stderr)
    print(f"  Visualize: snakeviz {os.path.abspath(prof_path)}", file=sys.stderr)
    print(
        f"  Or:        python -m pstats {os.path.abspath(prof_path)}", file=sys.stderr
    )
    print(f"{'=' * 60}\n", file=sys.stderr)

    # Quit automatically after GTK loop starts — no manual kill needed
    from gi.repository import GLib

    GLib.timeout_add(500, self.quit)

    return _original_run(self, *args, **kwargs)


try:
    from fabric import Application

    _original_run = Application.run
    Application.run = _patched_run
except ImportError:
    pass

# Run the app normally
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
)
from fabric_config.main import main  # noqa: E402

main()
