#!/usr/bin/env python3
"""Patch fabric component constructors to report per-component init time."""

import time
import sys
import os

_timings: list[tuple[str, float]] = []


def _patch_component(cls):
    orig_init = cls.__init__

    def timed_init(self, *args, **kwargs):
        t0 = time.monotonic()
        orig_init(self, *args, **kwargs)
        elapsed_ms = (time.monotonic() - t0) * 1000
        _timings.append((type(self).__name__, elapsed_ms))

    cls.__init__ = timed_init
    return cls


def _install_patches():
    try:
        from fabric_config.components.bar.bar import StatusBarSeperated, ScreenCorners
        from fabric_config.components.notification_popup import NotificationPopup
        from fabric_config.components.overview import Overview
        from fabric_config.components.app_menu import AppMenu
        from fabric_config.components.system_osd import SystemOSD

        for cls in (StatusBarSeperated, ScreenCorners, NotificationPopup, Overview, AppMenu, SystemOSD):
            _patch_component(cls)
    except Exception as e:
        print(f"[component_timer] patch error: {e}", file=sys.stderr)


def _print_report():
    if not _timings:
        return
    total = sum(ms for _, ms in _timings)
    print(f"\n{'='*50}", file=sys.stderr)
    print("Component init times:", file=sys.stderr)
    print(f"{'='*50}", file=sys.stderr)
    for name, ms in sorted(_timings, key=lambda x: -x[1]):
        bar = "#" * int(ms / 5)
        print(f"  {name:<30} {ms:7.1f} ms  {bar}", file=sys.stderr)
    print(f"  {'TOTAL':<30} {total:7.1f} ms", file=sys.stderr)
    print(f"{'='*50}\n", file=sys.stderr)


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))

try:
    from fabric import Application
    _orig_run = Application.run

    def _patched_run(self, *args, **kwargs):
        from gi.repository import GLib

        def _quit_with_report():
            _print_report()
            self.quit()
            return False

        GLib.timeout_add(3000, _quit_with_report)
        return _orig_run(self, *args, **kwargs)

    Application.run = _patched_run
except ImportError:
    pass

_install_patches()

from fabric_config.main import main  # noqa: E402

main()
