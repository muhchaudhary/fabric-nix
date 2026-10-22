from collections.abc import Callable, Sequence
from dataclasses import replace

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from gi.repository import Gtk

from fabric_config.components.quick_settings.widgets.quick_settings_submenu import (
    QuickSubMenu,
    QuickSubToggle,
)
from fabric_config.services.displays import SCALES, Display, Displays, Mode
from fabric_config.widgets.toggle_pill import ToggleSwitch


class Stepper(Box):
    """‹ value ›: steps through a list of options."""

    def __init__(self, on_change: Callable[[int], None], **kwargs):
        self._on_change = on_change
        self._labels: Sequence[str] = ()
        self._index = 0
        self.value = Label(name="display-stepper-value", h_expand=True)
        self.prev = Button(
            name="display-stepper-button",
            image=Image(icon_name="pan-start-symbolic", icon_size=14),
            on_clicked=lambda *_: self._step(-1),
        )
        self.next = Button(
            name="display-stepper-button",
            image=Image(icon_name="pan-end-symbolic", icon_size=14),
            on_clicked=lambda *_: self._step(1),
        )
        super().__init__(
            name="display-stepper",
            children=[self.prev, self.value, self.next],
            **kwargs,
        )

    def set_options(self, labels: Sequence[str], index: int):
        self._labels = labels
        self._index = max(0, min(index, len(labels) - 1))
        self.value.set_label(labels[self._index] if labels else "")
        self.prev.set_sensitive(self._index > 0)
        self.next.set_sensitive(self._index < len(labels) - 1)

    def _step(self, delta: int):
        index = self._index + delta
        if 0 <= index < len(self._labels):
            self._on_change(index)


def _resolutions(display: Display) -> list[tuple[int, int]]:
    seen: list[tuple[int, int]] = []
    for mode in display.modes:
        if (mode.width, mode.height) not in seen:
            seen.append((mode.width, mode.height))
    current = (display.mode.width, display.mode.height)
    if current not in seen:
        seen.insert(0, current)
    return seen


def _rates(display: Display) -> list[Mode]:
    rates = [
        m
        for m in display.modes
        if (m.width, m.height) == (display.mode.width, display.mode.height)
    ]
    if display.mode not in rates:
        rates.insert(0, display.mode)
    return sorted(rates, key=lambda m: -m.refresh)


def _scales(display: Display) -> list[float]:
    return sorted({*SCALES, display.scale})


class DisplayCard(Box):
    """One display's settings, staged until Apply."""

    def __init__(
        self,
        name: str,
        get: Callable[[str], Display],
        set: Callable[[Display], None],
        others: Callable[[str], list[str]],
        **kwargs,
    ):
        self.name = name
        self._get = get
        self._set = set
        self._others = others

        self.title = Label(
            style_classes=["submenu-card-label"],
            h_align="start",
            ellipsization="end",
            max_chars_width=26,
        )
        self.subtitle = Label(style_classes=["submenu-card-sublabel"], h_align="start")
        self.switch = ToggleSwitch(on_toggled=lambda on: self._update(disabled=not on))
        self.resolution = Stepper(self._pick_resolution)
        self.rate = Stepper(self._pick_rate)
        self.scale = Stepper(self._pick_scale)
        self.mirror = Stepper(self._pick_mirror)
        self.vrr = ToggleSwitch(on_toggled=lambda on: self._update(vrr_override=on))
        for switch in (self.switch, self.vrr):
            switch.set_valign(Gtk.Align.CENTER)
        self.mirror_row = self._row("Mirror", self.mirror)
        self.settings = Box(
            orientation="v",
            spacing=4,
            children=[
                self._row("Resolution", self.resolution),
                self._row("Refresh rate", self.rate),
                self._row("Scale", self.scale),
                self.mirror_row,
                self._row("Variable refresh", self.vrr, stretch=False),
            ],
        )
        self.settings_revealer = Revealer(
            child=self.settings, transition_type="slide-down", transition_duration=200
        )
        super().__init__(
            orientation="v",
            spacing=6,
            style_classes=["submenu-card", "display-card"],
            children=[
                CenterBox(
                    start_children=Box(
                        spacing=10,
                        children=[
                            Image(
                                icon_name="video-display-symbolic",
                                icon_size=16,
                                style_classes=["submenu-card-icon"],
                            ),
                            Box(
                                orientation="v",
                                children=[self.title, self.subtitle],
                            ),
                        ],
                    ),
                    end_children=self.switch,
                ),
                self.settings_revealer,
            ],
            **kwargs,
        )

    def _row(self, label: str, widget, stretch: bool = True) -> CenterBox:
        if stretch:
            widget.set_size_request(150, -1)
        return CenterBox(
            name="display-row",
            start_children=Label(label, style_classes=["submenu-card-sublabel"]),
            end_children=widget,
        )

    def sync(self):
        d = self._get(self.name)
        self.title.set_label(d.label)
        self.subtitle.set_label(
            f"{d.name} · Off"
            if d.disabled
            else f"{d.name} · Mirroring {d.mirror_of}"
            if d.mirror_of
            else f"{d.name} · {d.mode.resolution} · {d.mode.rate_label}"
        )
        if self.switch.get_active() == d.disabled:
            self.switch.set_active(not d.disabled)
        self.settings_revealer.set_reveal_child(not d.disabled)

        resolutions = _resolutions(d)
        self.resolution.set_options(
            [f"{w}×{h}" for w, h in resolutions],
            resolutions.index((d.mode.width, d.mode.height)),
        )
        rates = _rates(d)
        self.rate.set_options([m.rate_label for m in rates], rates.index(d.mode))
        scales = _scales(d)
        self.scale.set_options(
            [f"{round(s * 100)}%" for s in scales], scales.index(d.scale)
        )
        mirrors = [None, *self._others(self.name)]
        self.mirror_row.set_visible(len(mirrors) > 1 or d.mirror_of is not None)
        if d.mirror_of not in mirrors:
            mirrors.append(d.mirror_of)
        self.mirror.set_options(
            [m or "Off" for m in mirrors], mirrors.index(d.mirror_of)
        )
        vrr = d.vrr if d.vrr_override is None else d.vrr_override
        if self.vrr.get_active() != vrr:
            self.vrr.set_active(vrr)

    def _update(self, **changes):
        d = self._get(self.name)
        new = replace(d, **changes)
        if new != d:
            self._set(new)

    def _pick_resolution(self, index: int):
        d = self._get(self.name)
        width, height = _resolutions(d)[index]
        same_size = [m for m in d.modes if (m.width, m.height) == (width, height)]
        # keep the refresh rate if this size has it, else the fastest
        mode = next(
            (m for m in same_size if m.refresh == d.mode.refresh),
            max(same_size, key=lambda m: m.refresh, default=d.mode),
        )
        self._update(mode=mode)

    def _pick_rate(self, index: int):
        self._update(mode=_rates(self._get(self.name))[index])

    def _pick_scale(self, index: int):
        self._update(scale=_scales(self._get(self.name))[index])

    def _pick_mirror(self, index: int):
        mirrors = [None, *self._others(self.name)]
        self._update(mirror_of=mirrors[index] if index < len(mirrors) else None)


class DisplaysSubMenu(QuickSubMenu):
    def __init__(self, service: Displays, **kwargs):
        self.service = service
        # what's shown: the current settings plus any not applied yet
        self._staged: dict[str, Display] = {}
        self._cards: dict[str, DisplayCard] = {}

        self.cards_box = Box(orientation="v", spacing=4)
        self.apply_button = Button(
            label="Apply",
            name="display-apply",
            on_clicked=lambda *_: self._apply(),
        )
        self.reset_button = Button(
            label="Reset",
            name="display-reset",
            on_clicked=lambda *_: self._reset(),
        )
        self.apply_row = Box(
            spacing=6,
            h_align="end",
            children=[self.reset_button, self.apply_button],
        )
        self.confirm_label = Label(
            style_classes=["submenu-card-sublabel"], h_align="start", h_expand=True
        )
        self.confirm_row = Box(
            name="display-confirm",
            spacing=6,
            children=[
                self.confirm_label,
                Button(
                    label="Revert",
                    name="display-reset",
                    on_clicked=lambda *_: self.service.revert(),
                ),
                Button(
                    label="Keep",
                    name="display-apply",
                    on_clicked=lambda *_: self.service.keep(),
                ),
            ],
        )
        for row in (self.apply_row, self.confirm_row):
            row.set_no_show_all(True)

        super().__init__(
            title="Displays",
            title_icon="video-display-symbolic",
            child=Box(
                orientation="v",
                spacing=6,
                children=[
                    self.cards_box,
                    self.apply_row,
                    self.confirm_row,
                    Label(
                        "Until Hyprland's config is reloaded",
                        style_classes=["submenu-section-header"],
                        h_align="start",
                    ),
                ],
            ),
            **kwargs,
        )
        service.connect("notify::displays", lambda *_: self._reset())
        service.connect("notify::confirm-left", lambda *_: self._sync_buttons())
        self._reset()

    def _reset(self):
        self._staged = {d.name: d for d in self.service.displays}
        for name in [n for n in self._cards if n not in self._staged]:
            self._cards.pop(name).destroy()
        for name in self._staged:
            if name not in self._cards:
                card = self._cards[name] = DisplayCard(
                    name, self._staged.__getitem__, self._stage, self._mirror_targets
                )
                self.cards_box.add(card)
                card.show_all()
        self._sync()

    def _mirror_targets(self, name: str) -> list[str]:
        return [
            d.name
            for d in self._staged.values()
            if d.name != name and not d.disabled and d.mirror_of is None
        ]

    def _stage(self, display: Display):
        self._staged[display.name] = display
        self._sync()

    def _sync(self):
        for card in self._cards.values():
            card.sync()
        self._sync_buttons()

    def _dirty(self) -> bool:
        return any(d != self.service.get(d.name) for d in self._staged.values())

    def _sync_buttons(self):
        left = self.service.confirm_left
        self.confirm_row.set_visible(left > 0)
        self.confirm_label.set_label(f"Keep these settings? Undoing in {left} s")
        self.apply_row.set_visible(left == 0 and self._dirty())
        # can't turn every display off
        self.apply_button.set_sensitive(
            any(not d.disabled for d in self._staged.values())
        )

    def _apply(self):
        if not self.service.apply(list(self._staged.values())):
            self._reset()


class DisplaysToggle(QuickSubToggle):
    def __init__(self, submenu: DisplaysSubMenu, service: Displays, **kwargs):
        super().__init__(
            action_icon="video-display-symbolic",
            action_label="",
            title="Displays",
            submenu=submenu,
            **kwargs,
        )
        self.service = service
        # nothing to switch on or off: the tile opens the settings too
        self.connect("action-clicked", lambda *_: self.emit("reveal-clicked"))
        service.connect("notify::displays", self.update)
        service.connect("notify::confirm-left", self.update)
        self.update()

    def update(self, *_):
        on = [d for d in self.service.displays if not d.disabled]
        mirrored = [d for d in on if d.mirror_of]
        left = self.service.confirm_left
        if left:
            status = f"Keep changes? {left} s"
        elif mirrored:
            status = "Mirroring"
        elif len(on) == 1:
            status = f"{on[0].mode.resolution} · {on[0].mode.rate_label}"
        else:
            status = f"{len(on)} displays"
        self.set_action_label(status)
        self.set_active_style(bool(left))
