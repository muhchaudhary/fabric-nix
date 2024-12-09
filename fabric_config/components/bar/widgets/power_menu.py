from typing import Literal

from fabric.utils import exec_shell_command_async
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.widget import Widget

from fabric_config.widgets.popup_window_v2 import PopupWindow


class PowerMenuPopup(PopupWindow):
    def __init__(self):
        # State
        self.selected_operation: Literal["shutdown", "reboot", "lock"] | None = None

        # Props
        self.box_name = "prayer-info"
        self.button_name = "appmenu-button"
        self.icon_size = 150

        # Widgets
        self.confirm_menu: Revealer = Revealer(
            child=Box(
                orientation="v",
                children=[
                    Label("Are You Sure?"),
                    Button(
                        name=self.button_name,
                        label="YES",
                        on_clicked=lambda _: self.do_confirm(True),
                    ),
                    Button(
                        name=self.button_name,
                        label="NO",
                        style="background-color: red;",
                        on_clicked=lambda _: self.do_confirm(False),
                    ),
                ],
            ),
            transition_type="slide-down",
            notify_reveal_child=lambda _, child_reveal: self.set_action_buttons_focus(
                not self.confirm_menu.get_reveal_child()
            ),
        )

        self.menu = Box(
            name=self.box_name,
            orientation="v",
            children=[
                Box(
                    orientation="h",
                    children=[
                        Button(
                            name=self.button_name,
                            on_clicked=lambda button: self.on_button_press(
                                button, "shutdown"
                            ),
                            child=Box(
                                orientation="v",
                                children=[
                                    Image(
                                        icon_name="system-shutdown-symbolic",
                                        icon_size=self.icon_size,
                                    ),
                                    Label(label="Power Off"),
                                ],
                            ),
                        ),
                        Button(
                            name=self.button_name,
                            on_clicked=lambda button: self.on_button_press(
                                button, "lock"
                            ),
                            child=Box(
                                orientation="v",
                                children=[
                                    Image(
                                        icon_name="system-lock-screen-symbolic",
                                        icon_size=self.icon_size,
                                    ),
                                    Label("Lock", justification="right"),
                                ],
                            ),
                        ),
                        Button(
                            name=self.button_name,
                            on_clicked=lambda button: self.on_button_press(
                                button, "reboot"
                            ),
                            child=Box(
                                orientation="v",
                                children=[
                                    Image(
                                        icon_name="system-reboot-symbolic",
                                        icon_size=self.icon_size,
                                    ),
                                    Label("Reboot", justification="right"),
                                ],
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
        )

    def set_action_buttons_focus(self, can_focus: bool):
        for child in self.menu.children[0]:
            child: Widget = child
            child.set_can_focus(can_focus)

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
            self.toggle_popup()
        else:
            self.confirm_menu.set_reveal_child(False)

    def on_button_press(
        self, button: Button, pressed_button: Literal["shutdown", "reboot", "lock"]
    ):
        self.selected_operation = pressed_button
        self.confirm_menu.set_reveal_child(True)

    def toggle_popup(self, monitor: bool = False):
        self.selected_operation = None
        self.confirm_menu.set_reveal_child(False)
        self.set_action_buttons_focus(True)
        return super().toggle_popup(monitor=True)


class PowerMenuButton(Button):
    def __init__(self):
        self.powermenu_popup = PowerMenuPopup()
        super().__init__(
            name="panel-button",
            child=Image(
                icon_name="system-shutdown-symbolic",
                icon_size=20,
            ),
            on_button_press_event=lambda btn,
            event: self.powermenu_popup.toggle_popup(),
        )
