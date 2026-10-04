from dataclasses import dataclass

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from gi.repository import Gdk, Gio, GLib, Gtk
from loguru import logger

from fabric_config.utils.hyprland_monitor import get_hyprland_monitors
from fabric_config.utils.process import run_command_async
from fabric_config.widgets.popup_window_v2 import PopupWindow

TILE_ICON = 30
# how long an armed action waits for its second click
CONFIRM_S = 3.0


@dataclass(frozen=True)
class PowerAction:
    id: str
    label: str
    icon_name: str
    # the key that picks it while the menu is open
    key: int
    # destructive actions ask first; lock and suspend just happen
    confirm: bool
    # a logind Can* method that must answer "yes", or None
    logind_check: str | None = None


ACTIONS = [
    PowerAction("lock", "Lock", "changes-prevent-symbolic", Gdk.KEY_l, False),
    PowerAction(
        "suspend",
        "Suspend",
        "weather-clear-night-symbolic",
        Gdk.KEY_s,
        False,
        "CanSuspend",
    ),
    PowerAction(
        "hibernate",
        "Hibernate",
        "system-hibernate-symbolic",
        Gdk.KEY_h,
        True,
        "CanHibernate",
    ),
    PowerAction("logout", "Log Out", "system-log-out-symbolic", Gdk.KEY_e, True),
    PowerAction("reboot", "Reboot", "system-reboot-symbolic", Gdk.KEY_r, True),
    PowerAction("shutdown", "Power Off", "system-shutdown-symbolic", Gdk.KEY_p, True),
]


def logind_can(method: str) -> bool:
    """Ask logind whether an action is possible (e.g. hibernate needs swap)."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        reply = bus.call_sync(
            "org.freedesktop.login1",
            "/org/freedesktop/login1",
            "org.freedesktop.login1.Manager",
            method,
            None,
            GLib.VariantType("(s)"),
            Gio.DBusCallFlags.NONE,
            1000,
            None,
        )
    except GLib.Error as e:
        logger.warning(f"[PowerMenu] logind {method} failed: {e.message}")
        return False
    return reply.unpack()[0] == "yes"


def run_action(action_id: str):
    def report(success: bool, _stdout: str, stderr: str):
        if not success:
            logger.error(f"[PowerMenu] {action_id} failed: {stderr.strip()}")

    logger.info(f"[PowerMenu] executing {action_id}")
    match action_id:
        case "lock":
            run_command_async(["loginctl", "lock-session"], report)
        case "suspend":
            # hypridle locks the screen before sleeping
            run_command_async(["systemctl", "suspend"], report)
        case "hibernate":
            run_command_async(["systemctl", "hibernate"], report)
        case "logout":
            # Hyprland runs as a uwsm unit: stopping it ends the session
            # cleanly; exiting the compositor directly is the fallback
            if GLib.find_program_in_path("uwsm"):
                run_command_async(["uwsm", "stop"], report)
            else:
                get_hyprland_monitors().send_command("/dispatch hl.dsp.exit()")
        case "reboot":
            run_command_async(["systemctl", "reboot"], report)
        case "shutdown":
            run_command_async(["systemctl", "poweroff"], report)


class PowerTile(Button):
    """One action: an icon, its name and its key. Destructive ones arm first."""

    def __init__(self, action: PowerAction, **kwargs):
        self.action = action
        key = (Gdk.keyval_name(action.key) or "").upper()
        self.label = Label(action.label, name="powermenu-tile-label")
        # counts down while armed: click again (or Enter) before it runs out
        self.countdown = Gtk.LevelBar(min_value=0, max_value=1, value=1)
        self.countdown.set_name("powermenu-countdown")
        self.countdown.set_no_show_all(True)
        super().__init__(
            name="powermenu-tile",
            tooltip_text=f"{action.label} ({key})",
            child=Overlay(
                child=Box(
                    orientation="v",
                    spacing=8,
                    v_align="center",
                    children=[
                        Image(icon_name=action.icon_name, icon_size=TILE_ICON),
                        self.label,
                        self.countdown,
                    ],
                ),
                overlays=Label(
                    key, name="powermenu-key", h_align="end", v_align="start"
                ),
            ),
            **kwargs,
        )
        if action.confirm:
            self.add_style_class("destructive")

    def set_armed(self, armed: bool):
        self.label.set_label("Click again" if armed else self.action.label)
        self.countdown.set_visible(armed)
        self.countdown.set_value(1)
        if armed:
            self.add_style_class("armed")
        else:
            self.remove_style_class("armed")


class PowerMenuPopup(PopupWindow):
    def __init__(self):
        self.armed: PowerTile | None = None
        self._armed_at = 0
        self._tick: int | None = None
        self.tiles = [
            PowerTile(action, on_clicked=self.on_tile_clicked)
            for action in ACTIONS
            if action.logind_check is None or logind_can(action.logind_check)
        ]
        self.hint = Label(
            "Press a key, or click · destructive actions ask twice",
            name="powermenu-hint",
        )
        self.menu = Box(
            name="powermenu-box",
            orientation="v",
            spacing=12,
            children=[Box(spacing=10, children=self.tiles), self.hint],
        )
        super().__init__(
            transition_type="crossfade",
            child=self.menu,
            anchor="center",
            keyboard_mode="on-demand",
            enable_inhibitor=True,
        )
        self.connect("key-press-event", self.on_key_press)

    # Arming

    def on_tile_clicked(self, tile: PowerTile):
        if not tile.action.confirm or tile is self.armed:
            self._run(tile)
            return
        self.disarm()
        self.armed = tile
        tile.set_armed(True)
        self._armed_at = GLib.get_monotonic_time()
        self._tick = tile.add_tick_callback(self._count_down)

    def _count_down(self, tile: PowerTile, clock: Gdk.FrameClock) -> bool:
        elapsed = (clock.get_frame_time() - self._armed_at) / 1_000_000
        remaining = 1 - elapsed / CONFIRM_S
        if remaining <= 0:
            self._tick = None
            self.disarm()
            return False
        tile.countdown.set_value(remaining)
        return True

    def disarm(self):
        if self.armed is not None:
            if self._tick is not None:
                self.armed.remove_tick_callback(self._tick)
                self._tick = None
            self.armed.set_armed(False)
            self.armed = None

    def _run(self, tile: PowerTile):
        self.disarm()
        self.toggle_popup()
        run_action(tile.action.id)

    # Keys

    def on_key_press(self, _, event: Gdk.EventKey) -> bool:
        if not self.popup_visible:
            return False
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.armed is not None:
                self._run(self.armed)
                return True
            return False
        keyval = Gdk.keyval_to_lower(event.keyval)
        for tile in self.tiles:
            if tile.action.key == keyval:
                self.on_tile_clicked(tile)
                return True
        return False

    def on_key_release(self, widget, event_key: Gdk.EventKey):
        # Escape backs out of an armed action first; the menu stays open
        if event_key.keyval == Gdk.KEY_Escape and self.armed is not None:
            self.disarm()
            return
        super().on_key_release(widget, event_key)

    def toggle_popup(self, monitor: bool = False):
        self.disarm()
        return super().toggle_popup(monitor=True)


_power_menu: PowerMenuPopup | None = None


def get_power_menu() -> PowerMenuPopup:
    """The one power menu, opened from the bar and from quick settings."""
    global _power_menu
    if _power_menu is None:
        _power_menu = PowerMenuPopup()
    return _power_menu


class PowerMenuButton(Button):
    def __init__(self):
        self.powermenu_popup = get_power_menu()
        super().__init__(
            style_classes=["button-basic", "button-basic-props", "button-border"],
            child=Image(
                icon_name="system-shutdown-symbolic",
                icon_size=20,
            ),
            on_clicked=lambda *_: [
                self.powermenu_popup.toggle_popup(),
                self.add_style_class("button-basic-active"),
            ],
        )

        self.powermenu_popup.reveal_child.revealer.connect(
            "notify::reveal-child",
            lambda *args: (
                [
                    self.add_style_class("button-basic-active"),
                    self.remove_style_class("button-basic"),
                ]
                if self.powermenu_popup.popup_visible
                else [
                    self.remove_style_class("button-basic-active"),
                    self.add_style_class("button-basic"),
                ]
            ),
        )
