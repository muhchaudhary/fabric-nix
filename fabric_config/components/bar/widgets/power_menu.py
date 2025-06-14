from typing import Literal

from fabric.utils import exec_shell_command_async
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.widget import Widget

from fabric_config.widgets.popup_window_v2 import PopupWindow


class PowerMenuActionButton(Button):
    def __init__(self, action_name: str, icon_name: str, icon_size: int, **kwargs):
        super().__init__(
            style_classes=["button-basic", "button-basic-props", "button-border"],
            child=Box(
                orientation="v",
                children=[
                    Image(icon_name=icon_name, icon_size=icon_size),
                    Label(action_name),
                ],
            ),
            **kwargs,
        )


class PowerMenuConfirmMenu(Revealer):
    def __init__(self, popup: PopupWindow, **kwargs):
        self.active_button: Button | None = None
        self.selected_operation: str | None = None
        self.popup: PopupWindow = popup

        button_name = "powermenu-button"
        super().__init__(
            child=Box(
                orientation="v",
                children=[
                    Label("Are You Sure?"),
                    Button(
                        name=button_name,
                        style_classes=[
                            "button-basic",
                            "button-basic-props",
                            "button-border",
                            "warning",
                        ],
                        label="YES",
                        on_clicked=lambda _: self.do_confirm(True),
                    ),
                    Button(
                        name=button_name,
                        label="NO",
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
        selected_operation: str | None = None,
    ):
        if active_button and self.active_button:
            return

        if active_button:
            active_button.add_style_class("active") if active_button else None
        else:
            self.active_button.remove_style_class(
                "button-basic-active"
            ) if self.active_button else None

        self.selected_operation = selected_operation
        self.active_button = active_button
        self.set_reveal_child(reveal_menu)

    def do_confirm(self, confirmation: bool):
        if confirmation:
            print(f"Okay lets go, {self.selected_operation}")
            match self.selected_operation:
                case "shutdown":
                    exec_shell_command_async("shutdown now")
                case "reboot":
                    exec_shell_command_async("reboot")
                case "lock":
                    exec_shell_command_async("bash -c 'pidof hyprlock || hyprlock'")
            self.popup.toggle_popup()
        else:
            self.reveal_menu(False)


class PowerMenuPopup(PopupWindow):
    def __init__(self):
        # State
        self.selected_operation: Literal["shutdown", "reboot", "lock"] | None = None

        # Props
        box_name = "powermenu-box"

        # Widgets
        self.confirm_menu = PowerMenuConfirmMenu(
            self,
            notify_reveal_child=lambda _, child_reveal: self.set_action_buttons_focus(
                not self.confirm_menu.get_reveal_child()
            ),
        )
        self.menu = Box(
            name=box_name,
            orientation="v",
            children=[
                Box(
                    children=[
                        PowerMenuActionButton(
                            action_name="Power Off",
                            icon_name="system-shutdown-symbolic",
                            icon_size=150,
                            on_clicked=lambda button: self.on_button_press(
                                button, "shutdown"
                            ),
                        ),
                        PowerMenuActionButton(
                            action_name="Lock",
                            icon_name="system-lock-screen-symbolic",
                            icon_size=150,
                            on_clicked=lambda button: self.on_button_press(
                                button, "lock"
                            ),
                        ),
                        PowerMenuActionButton(
                            action_name="Reboot",
                            icon_name="system-reboot-symbolic",
                            icon_size=150,
                            on_clicked=lambda button: self.on_button_press(
                                button, "reboot"
                            ),
                        ),
                    ],
                ),
                self.confirm_menu,
            ],
        )

        # Setup
        super().__init__(
            transition_type="crossfade",
            child=self.menu,
            anchor="center",
            keyboard_mode="on-demand",
            enable_inhibitor=True,
        )

    def set_action_buttons_focus(self, can_focus: bool):
        for child in self.menu.children[0]:
            child.set_sensitive(can_focus)

    def on_button_press(
        self, button: Button, pressed_button: Literal["shutdown", "reboot", "lock"]
    ):
        button.add_style_class("button-basic-active")
        self.confirm_menu.reveal_menu(True, button, pressed_button)

    def toggle_popup(self, monitor: bool = False):
        self.selected_operation = None
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
            lambda *args: [
                self.add_style_class("button-basic-active"),
                self.remove_style_class("button-basic"),
            ]
            if self.powermenu_popup.popup_visible
            else [
                self.remove_style_class("button-basic-active"),
                self.add_style_class("button-basic"),
            ],
        )
