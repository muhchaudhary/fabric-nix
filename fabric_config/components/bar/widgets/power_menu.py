from dataclasses import dataclass

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from gi.repository import Gdk, Gio, GLib
from loguru import logger

from fabric_config.utils.hyprland_monitor import get_hyprland_monitors
from fabric_config.utils.process import run_command_async
from fabric_config.widgets.popup_window_v2 import PopupWindow


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
    PowerAction("lock", "Lock", "system-lock-screen-symbolic", Gdk.KEY_l, False),
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
        "drive-harddisk-symbolic",
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


class PowerMenuActionButton(Button):
    def __init__(self, action: PowerAction, icon_size: int, **kwargs):
        self.action = action
        super().__init__(
            style_classes=["button-basic", "button-basic-props", "button-border"],
            tooltip_text=f"{action.label} ({Gdk.keyval_name(action.key).upper()})",  # type: ignore
            child=Box(
                orientation="v",
                children=[
                    Image(icon_name=action.icon_name, icon_size=icon_size),
                    Label(action.label),
                ],
            ),
            **kwargs,
        )


class PowerMenuConfirmMenu(Revealer):
    def __init__(self, popup: "PowerMenuPopup", **kwargs):
        self.active_button: Button | None = None
        self.selected: PowerAction | None = None
        self.popup = popup

        button_name = "powermenu-button"
        self.question = Label("Are You Sure?")
        super().__init__(
            child=Box(
                orientation="v",
                children=[
                    self.question,
                    Button(
                        name=button_name,
                        style_classes=[
                            "button-basic",
                            "button-basic-props",
                            "button-border",
                            "warning",
                        ],
                        label="YES  (Enter)",
                        on_clicked=lambda _: self.do_confirm(True),
                    ),
                    Button(
                        name=button_name,
                        label="NO  (Esc)",
                        style_classes=[
                            "button-basic",
                            "button-basic-props",
                            "button-border",
                            "okay",
                        ],
                        on_clicked=lambda _: self.do_confirm(False),
                    ),
                ],
            ),
            transition_type="slide-down",
            **kwargs,
        )

    def reveal_menu(
        self,
        reveal_menu: bool,
        active_button: Button | None = None,
        selected: PowerAction | None = None,
    ):
        if active_button and self.active_button:
            return

        if active_button:
            active_button.add_style_class("button-basic-active")
        elif self.active_button:
            self.active_button.remove_style_class("button-basic-active")

        if selected:
            self.question.set_label(f"{selected.label}?")
        self.selected = selected
        self.active_button = active_button
        self.set_reveal_child(reveal_menu)

    def do_confirm(self, confirmation: bool):
        if confirmation and self.selected:
            selected = self.selected
            self.popup.toggle_popup()
            run_action(selected.id)
        else:
            self.reveal_menu(False)


class PowerMenuPopup(PopupWindow):
    def __init__(self):
        self.confirm_menu = PowerMenuConfirmMenu(
            self,
            notify_reveal_child=lambda *_: self.set_action_buttons_focus(
                not self.confirm_menu.get_reveal_child()
            ),
        )
        self.action_buttons = Box(
            children=[
                PowerMenuActionButton(
                    action=action,
                    icon_size=96,
                    on_clicked=self.on_button_press,
                )
                for action in ACTIONS
                if action.logind_check is None or logind_can(action.logind_check)
            ],
        )
        self.menu = Box(
            name="powermenu-box",
            orientation="v",
            children=[self.action_buttons, self.confirm_menu],
        )

        super().__init__(
            transition_type="crossfade",
            child=self.menu,
            anchor="center",
            keyboard_mode="on-demand",
            enable_inhibitor=True,
        )
        self.connect("key-press-event", self.on_key_press)

    @property
    def buttons(self) -> list[PowerMenuActionButton]:
        return self.action_buttons.children  # type: ignore

    def set_action_buttons_focus(self, can_focus: bool):
        for child in self.buttons:
            child.set_sensitive(can_focus)

    def on_button_press(self, button: PowerMenuActionButton):
        if button.action.confirm:
            self.confirm_menu.reveal_menu(True, button, button.action)
        else:
            self.toggle_popup()
            run_action(button.action.id)

    def on_key_press(self, _, event: Gdk.EventKey) -> bool:
        if not self.popup_visible:
            return False
        if self.confirm_menu.get_reveal_child():
            if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                self.confirm_menu.do_confirm(True)
                return True
            return False
        keyval = Gdk.keyval_to_lower(event.keyval)
        for button in self.buttons:
            if button.action.key == keyval:
                self.on_button_press(button)
                return True
        return False

    def on_key_release(self, widget, event_key: Gdk.EventKey):
        # Escape backs out of the question first; the popup stays open
        if event_key.keyval == Gdk.KEY_Escape and self.confirm_menu.get_reveal_child():
            self.confirm_menu.do_confirm(False)
            return
        super().on_key_release(widget, event_key)

    def toggle_popup(self, monitor: bool = False):
        self.confirm_menu.reveal_menu(False)
        self.set_action_buttons_focus(True)
        return super().toggle_popup(monitor=True)


class PowerMenuButton(Button):
    def __init__(self):
        self.powermenu_popup = PowerMenuPopup()
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
