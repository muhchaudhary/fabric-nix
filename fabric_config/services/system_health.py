"""
Things about the system worth knowing about: failed systemd units (system
and user), NixOS pins not updated in a while, a nearly full /nix/store, and
a kernel update waiting for a reboot.

`config.system_health` checks every few minutes (and when asked) and emits
`changed`; `issues` is what's wrong right now, minus what was dismissed. A
dismissed issue stays hidden until it clears, then comes back if it recurs.
"""

import datetime
import json
import os
import shutil
from dataclasses import dataclass

from fabric.core.service import Service, Signal
from gi.repository import GLib
from loguru import logger

from fabric_config.utils.process import run_command_async

CHECK_EVERY_S = 5 * 60
# give startup a moment before the first check
FIRST_CHECK_S = 20
# the pins (or flake.lock) the system is built from; npins update rewrites
# the file, so its age is how long since the inputs were updated
PINS_FILES = [
    os.environ.get("FABRIC_PINS_FILE", ""),
    os.path.expanduser("~/nixOS/DesktopConfig/npins/sources.json"),
    "/etc/nixos/flake.lock",
]
STALE_PINS_DAYS = 14
STORE = "/nix/store"
LOW_DISK_FRACTION = 0.10
LOW_DISK_BYTES = 20 * 1024**3
DISMISSED_FILE = os.path.join(
    GLib.get_user_cache_dir(), "fabric", "system_health_dismissed.json"
)


@dataclass(frozen=True)
class Issue:
    key: str  # stable while the issue lasts (dismissals use it)
    kind: str  # "unit", "pins", "disk" or "reboot"
    title: str
    detail: str
    unit: str | None = None
    user: bool = False  # a user unit (systemctl --user)


class SystemHealth(Service):
    @Signal
    def changed(self) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._all: list[Issue] = []
        self._units: dict[bool, list[Issue]] = {False: [], True: []}
        # which unit lists (system, user) have come in at least once
        self._units_seen: set[bool] = set()
        self._dismissed: set[str] = self._load_dismissed()
        GLib.timeout_add_seconds(FIRST_CHECK_S, lambda: self.refresh() or False)
        GLib.timeout_add_seconds(CHECK_EVERY_S, lambda: self.refresh() or True)

    @property
    def issues(self) -> list[Issue]:
        return [i for i in self._all if i.key not in self._dismissed]

    def dismiss(self, issue: Issue):
        self._dismissed.add(issue.key)
        self._save_dismissed()
        self.changed()

    def refresh(self):
        for user in (False, True):
            self._check_units(user)
        self._publish()

    # Checks

    def _check_units(self, user: bool):
        argv = ["systemctl", *(["--user"] if user else [])]
        argv += ["list-units", "--state=failed", "--output=json", "--no-pager"]

        def on_done(success: bool, stdout: str, stderr: str):
            if not success:
                logger.warning(f"[SystemHealth] {' '.join(argv[:2])}: {stderr.strip()}")
                return
            try:
                units = json.loads(stdout or "[]")
            except ValueError:
                return
            self._units_seen.add(user)
            self._units[user] = [
                Issue(
                    key=f"unit:{'user' if user else 'system'}:{u['unit']}",
                    kind="unit",
                    title=f"{u['unit']} failed",
                    detail=(u.get("description") or "") + (" (user)" if user else ""),
                    unit=u["unit"],
                    user=user,
                )
                for u in units
                if u.get("unit")
            ]
            self._publish()

        run_command_async(argv, on_done)

    def _check_pins(self) -> Issue | None:
        path = next((p for p in PINS_FILES if p and os.path.exists(p)), None)
        if path is None:
            return None
        updated = datetime.datetime.fromtimestamp(os.path.getmtime(path))
        days = (datetime.datetime.now() - updated).days
        if days < STALE_PINS_DAYS:
            return None
        return Issue(
            key=f"pins:{path}:{updated.date().isoformat()}",
            kind="pins",
            title=f"System inputs are {days} days old",
            detail=f"{_short_path(path)} last updated {updated:%b %-d}",
        )

    def _check_disk(self) -> Issue | None:
        try:
            usage = shutil.disk_usage(STORE)
        except OSError:
            return None
        if usage.free >= min(LOW_DISK_BYTES, usage.total * LOW_DISK_FRACTION):
            return None
        return Issue(
            key="disk:store",
            kind="disk",
            title="Nix store disk nearly full",
            detail=f"{usage.free / 1024**3:.1f} GB free of {usage.total / 1024**3:.0f} GB",
        )

    def _check_reboot(self) -> Issue | None:
        booted = os.path.realpath("/run/booted-system/kernel")
        current = os.path.realpath("/run/current-system/kernel")
        if not os.path.exists(booted) or booted == current:
            return None
        return Issue(
            key=f"reboot:{current}",
            kind="reboot",
            title="Reboot to use the new kernel",
            detail="The running kernel is older than the current system's",
        )

    def _publish(self):
        issues = [*self._units[False], *self._units[True]]
        issues += [
            i
            for i in (self._check_pins(), self._check_disk(), self._check_reboot())
            if i is not None
        ]
        # forget dismissals of issues that cleared, so a recurrence shows
        keys = {i.key for i in issues}
        # (only once both unit lists are in: before that, a unit issue that's
        # missing hasn't cleared, it just hasn't been looked for)
        if self._dismissed - keys and len(self._units_seen) == 2:
            self._dismissed &= keys
            self._save_dismissed()
        if issues != self._all:
            self._all = issues
            self.changed()

    # Dismissals

    def _load_dismissed(self) -> set[str]:
        try:
            with open(DISMISSED_FILE) as f:
                return set(json.load(f))
        except (OSError, ValueError, TypeError):
            return set()

    def _save_dismissed(self):
        try:
            os.makedirs(os.path.dirname(DISMISSED_FILE), exist_ok=True)
            with open(DISMISSED_FILE, "w") as f:
                json.dump(sorted(self._dismissed), f)
        except OSError as e:
            logger.warning(f"[SystemHealth] Couldn't save dismissals: {e}")


def _short_path(path: str) -> str:
    home = os.path.expanduser("~")
    return "~" + path[len(home) :] if path.startswith(home) else path
