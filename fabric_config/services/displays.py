"""
Displays: Hyprland's outputs, and changing their mode, scale, VRR, mirroring
or whether they're on.

Changes go through `hl.monitor()` (Hyprland's Lua config), so they last until
the config is reloaded. A change can leave a screen black, so like GNOME it's
undone after CONFIRM_SECONDS unless kept.
"""

import json
from dataclasses import dataclass, field, replace

from fabric.core.service import Property, Service, Signal
from gi.repository import GLib
from loguru import logger

from fabric_config.utils.hyprland_monitor import get_hyprland_events

CONFIRM_SECONDS = 15
SCALES = (1.0, 1.25, 1.5, 1.75, 2.0)


@dataclass(frozen=True)
class Mode:
    width: int
    height: int
    refresh: float

    @classmethod
    def parse(cls, text: str) -> "Mode | None":
        # "2560x1440@75.00Hz"
        try:
            size, rate = text.removesuffix("Hz").split("@")
            width, height = size.split("x")
            return cls(int(width), int(height), round(float(rate), 2))
        except ValueError:
            return None

    @property
    def resolution(self) -> str:
        return f"{self.width}×{self.height}"

    @property
    def rate_label(self) -> str:
        return f"{self.refresh:g} Hz"

    def to_rule(self) -> str:
        return f"{self.width}x{self.height}@{self.refresh:g}"


@dataclass(frozen=True)
class Display:
    name: str
    description: str
    mode: Mode
    modes: tuple[Mode, ...]
    x: int
    y: int
    scale: float
    transform: int
    vrr: bool
    disabled: bool
    mirror_of: str | None
    focused: bool = field(default=False, compare=False)
    # VRR set here; None leaves it to the config (often the global misc:vrr)
    vrr_override: bool | None = None

    @property
    def label(self) -> str:
        return self.description or self.name

    @property
    def logical_size(self) -> tuple[int, int]:
        w, h = round(self.mode.width / self.scale), round(self.mode.height / self.scale)
        return (h, w) if self.transform % 2 else (w, h)

    def to_lua(self) -> str:
        if self.disabled:
            return f'hl.monitor({{ output = "{self.name}", disabled = true }})'
        fields = [
            f'output = "{self.name}"',
            f'mode = "{self.mode.to_rule()}"',
            f'position = "{self.x}x{self.y}"',
            f"scale = {self.scale:g}",
            f"transform = {self.transform}",
        ]
        if self.vrr_override is not None:
            fields.append(f"vrr = {1 if self.vrr_override else 0}")
        if self.mirror_of:
            fields.append(f'mirror = "{self.mirror_of}"')
        return "hl.monitor({ " + ", ".join(fields) + " })"


def _parse(monitor: dict) -> Display | None:
    modes = tuple(
        m for m in (Mode.parse(t) for t in monitor.get("availableModes", [])) if m
    )
    current = Mode(
        monitor.get("width", 0),
        monitor.get("height", 0),
        round(float(monitor.get("refreshRate", 0)), 2),
    )
    if monitor.get("disabled") or not current.width:
        # off: offer its preferred (first) mode for when it's turned on
        current = modes[0] if modes else current
    mirror = monitor.get("mirrorOf")
    return Display(
        name=monitor["name"],
        description=" ".join(
            p for p in (monitor.get("make"), monitor.get("model")) if p
        ).strip(),
        mode=current,
        modes=modes,
        x=monitor.get("x", 0),
        y=monitor.get("y", 0),
        scale=float(monitor.get("scale", 1)),
        transform=monitor.get("transform", 0),
        vrr=bool(monitor.get("vrr")),
        disabled=bool(monitor.get("disabled")),
        mirror_of=None if mirror in (None, "", "none") else mirror,
        focused=bool(monitor.get("focused")),
    )


def _pack_in_a_row(displays: list[Display], current: list[Display]) -> list[Display]:
    """
    Lay the shown displays out left to right, in their current order (ones
    being turned on go last), so a change of size leaves no gap or overlap.
    Only for setups that are a single row: anything else was arranged by hand
    and is left alone.
    """
    was_shown = {d.name for d in current if not d.disabled and not d.mirror_of}
    shown = [d for d in displays if not d.disabled and not d.mirror_of]
    if len({d.y for d in shown if d.name in was_shown}) > 1:
        return displays
    x = 0
    placed: dict[str, Display] = {}
    for d in sorted(shown, key=lambda d: (d.name not in was_shown, d.x)):
        placed[d.name] = replace(d, x=x, y=0)
        x += d.logical_size[0]
    return [placed.get(d.name, d) for d in displays]


class Displays(Service):
    @Signal
    def changed(self) -> None: ...

    def __init__(self, **kwargs):
        self._displays: list[Display] = []
        # VRR set from here, by output; a config reload drops them
        self._vrr: dict[str, bool] = {}
        self._previous: list[Display] | None = None
        self._confirm_left = 0
        self._confirm_source: int | None = None
        super().__init__(**kwargs)
        self._connection = get_hyprland_events()
        for event in ("monitoraddedv2", "monitorremovedv2"):
            self._connection.connect(f"event::{event}", lambda *_: self.refresh())
        self._connection.connect("event::configreloaded", self._on_config_reloaded)
        self.refresh()

    @Property(list, "readable")
    def displays(self) -> list[Display]:
        """Real outputs (not headless ones), enabled or not."""
        return self._displays

    @Property(int, "readable", default_value=0)
    def confirm_left(self) -> int:
        """Seconds until the last change is undone; 0 when nothing's pending."""
        return self._confirm_left

    def get(self, name: str) -> Display | None:
        return next((d for d in self._displays if d.name == name), None)

    def refresh(self):
        try:
            monitors = json.loads(self._connection.send_command("j/monitors all").reply)
        except Exception as e:
            logger.error(f"[Displays] Couldn't read monitors: {e}")
            return
        displays = [
            replace(d, vrr_override=self._vrr.get(d.name))
            for d in (_parse(m) for m in monitors)
            if d and not d.name.startswith("HEADLESS")
        ]
        if displays != self._displays:
            self._displays = displays
            self.notify("displays")
            self.changed()

    def apply(self, wanted: list[Display]) -> bool:
        """Apply new settings (all displays); undone unless keep() is called."""
        if not any(not d.disabled for d in wanted):
            logger.warning("[Displays] Refusing to turn every display off")
            return False
        changed = [
            d for d in _pack_in_a_row(wanted, self._displays) if d != self.get(d.name)
        ]
        if not changed:
            return True
        previous = self._previous or list(self._displays)
        if not self._eval(changed):
            return False
        self._previous = previous
        self._remember_vrr(wanted)
        self._start_countdown()
        GLib.timeout_add(500, lambda: self.refresh() and False)
        return True

    def keep(self):
        self._stop_countdown()
        self._previous = None

    def revert(self):
        previous, self._previous = self._previous, None
        self._stop_countdown()
        if previous is not None:
            self.refresh()
            changed = [d for d in previous if d != self.get(d.name)]
            # turn things back on before turning anything off
            ordered = sorted(changed, key=lambda d: d.disabled)
            if ordered:
                self._eval(ordered)
            self._remember_vrr(previous)
            GLib.timeout_add(500, lambda: self.refresh() and False)

    def _remember_vrr(self, displays: list[Display]):
        self._vrr = {
            d.name: d.vrr_override for d in displays if d.vrr_override is not None
        }

    def _on_config_reloaded(self, *_):
        # the config's own monitor rules are back; nothing here is pending
        self._vrr.clear()
        self.keep()
        self.refresh()

    def _eval(self, displays: list[Display]) -> bool:
        code = "; ".join(d.to_lua() for d in displays)
        reply = self._connection.send_command(f"/eval {code}").reply.decode()
        if reply.strip() != "ok":
            logger.error(f"[Displays] {code} -> {reply.strip()}")
            return False
        logger.info(f"[Displays] {code}")
        return True

    def _start_countdown(self):
        self._stop_countdown()
        self._confirm_left = CONFIRM_SECONDS
        self.notify("confirm-left")
        self._confirm_source = GLib.timeout_add_seconds(1, self._tick)

    def _stop_countdown(self):
        if self._confirm_source is not None:
            GLib.source_remove(self._confirm_source)
            self._confirm_source = None
        if self._confirm_left:
            self._confirm_left = 0
            self.notify("confirm-left")

    def _tick(self) -> bool:
        self._confirm_left -= 1
        self.notify("confirm-left")
        if self._confirm_left > 0:
            return True
        self._confirm_source = None
        logger.info("[Displays] Not kept; undoing")
        self.revert()
        return False
