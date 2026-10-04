from collections.abc import Callable

import gi
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.image import Image

import fabric_config.config as config
from fabric_config.components.quick_settings.widgets.quick_settings_submenu import (
    QuickSubToggle,
)
from fabric_config.components.quick_settings.widgets.sliders import (
    AudioSlider,
    BrightnessSlider,
)
from fabric_config.components.quick_settings.widgets.submenus import (
    BluetoothSubMenu,
    BluetoothToggle,
    NightLightSubMenu,
    NightLightToggle,
    WifiSubMenu,
    WifiToggle,
)
from fabric_config.components.bar.widgets.power_menu import get_power_menu
from fabric_config.components.bar.widgets.stats import format_uptime
from fabric_config.utils.process import run_command_async
from fabric_config.widgets.player import PlayerBoxStack
from fabric_config.widgets.popup_window_v2 import PopupWindow
from fabric_config.components.quick_settings.widgets.buttons.system_toggles import (
    CaffeineToggle,
    DoNotDisturbToggle,
    PowerProfileRow,
    ScreenRecordToggle,
    ScreenshotButton,
)
from fabric_config.components.quick_settings.widgets.buttons.theme_toggle import (
    ThemeToggle,
)

gi.require_version("AstalNetwork", "0.1")
from gi.repository import AstalNetwork as an  # noqa: E402
from gi.repository import GObject, Gtk  # noqa: E402


class QuickSettingsButtonBox(Gtk.Grid):
    def __init__(self, **kwargs):
        # a grid with equal columns keeps every toggle the same size, across
        # rows too; each submenu spans both columns, right below its row
        # (rows whose submenu is closed are empty, and get no spacing)
        super().__init__(
            row_spacing=8,
            column_spacing=8,
            column_homogeneous=True,
            **kwargs,
        )
        self.active_submenu = None

        # Wifi
        wifi_submenu = WifiSubMenu(config.network)
        self.wifi_toggle = WifiToggle(
            submenu=wifi_submenu,
            client=config.network,
        )

        # Bluetooth
        bluetooth_submenu = BluetoothSubMenu(config.bluetooth_client)
        self.bluetooth_toggle = BluetoothToggle(
            submenu=bluetooth_submenu,
            client=config.bluetooth_client,
        )

        # Night light (hyprsunset), beside the theme toggle on a second row
        night_light_submenu = NightLightSubMenu(config.hyprsunset)
        self.night_light_toggle = NightLightToggle(
            submenu=night_light_submenu,
            client=config.hyprsunset,
        )
        self.theme_toggle = ThemeToggle()

        # the popup is made after this box, so look it up when clicked
        def close_popup():
            if QuickSettingsPopup.popup_visible:
                QuickSettingsPopup.toggle_popup()

        self.dnd_toggle = DoNotDisturbToggle()
        self.caffeine_toggle = CaffeineToggle()
        self.record_toggle = ScreenRecordToggle(close_popup)
        self.screenshot_button = ScreenshotButton(close_popup)
        self.power_profile_row = PowerProfileRow()

        self.wifi_toggle.connect("reveal-clicked", self.set_active_submenu)
        self.bluetooth_toggle.connect("reveal-clicked", self.set_active_submenu)
        self.night_light_toggle.connect("reveal-clicked", self.set_active_submenu)

        rows: list[tuple[Gtk.Widget, ...]] = [
            (self.wifi_toggle, self.bluetooth_toggle),
            (wifi_submenu,),
            (bluetooth_submenu,),
            (self.night_light_toggle, self.theme_toggle),
            (night_light_submenu,),
            (self.dnd_toggle, self.caffeine_toggle),
            (self.record_toggle, self.screenshot_button),
            (self.power_profile_row,),
        ]
        for top, row in enumerate(rows):
            for left, widget in enumerate(row):
                widget.set_hexpand(True)
                self.attach(widget, left, top, 2 // len(row), 1)
        # plain GTK widgets start hidden, unlike fabric's
        self.show()

    def set_active_submenu(self, btn: QuickSubToggle | AudioSlider):
        if btn.submenu != self.active_submenu and self.active_submenu is not None:
            self.active_submenu.do_reveal(False)

        self.active_submenu = btn.submenu
        self.active_submenu.toggle_reveal() if self.active_submenu else None


class QuickSettings(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="v",
            spacing=10,
            h_expand=True,
            style_classes=["cool-border"],
            name="quicksettings",
            **kwargs,
        )
        self.mprisBox = PlayerBoxStack(config.mprisplayer)
        self.screen_bright_slider = BrightnessSlider(config.brightness)
        self.audio_slider_box = AudioSlider(config.audio)
        self.buttons_box = QuickSettingsButtonBox()

        self.audio_slider_box.reveal_button.connect(
            "clicked",
            lambda *_: self.buttons_box.set_active_submenu(self.audio_slider_box),
        )

        self.uptime = Label("", name="quicksettings-uptime", h_align="start")
        self.add(
            CenterBox(
                name="quicksettings-header",
                start_children=self.uptime,
                end_children=Box(
                    spacing=6,
                    children=[
                        self._header_button(
                            "changes-prevent-symbolic",
                            "Lock",
                            lambda: run_command_async(["loginctl", "lock-session"]),
                        ),
                        self._header_button(
                            "system-shutdown-symbolic",
                            "Power",
                            lambda: get_power_menu().toggle_popup(),
                        ),
                    ],
                ),
            )
        )
        self.connect("map", lambda *_: self.uptime.set_label(format_uptime()))
        self.add(self.buttons_box)
        self.add(self.audio_slider_box)
        self.add(self.audio_slider_box.submenu)
        self.add(self.screen_bright_slider)
        self.add(self.mprisBox)

    def _header_button(
        self, icon_name: str, tooltip: str, action: Callable[[], object]
    ) -> Button:
        def clicked(*_):
            QuickSettingsPopup.toggle_popup()
            action()

        return Button(
            name="quicksettings-header-button",
            tooltip_text=tooltip,
            image=Image(icon_name=icon_name, icon_size=16),
            on_clicked=clicked,
        )


class QuickSettingsButton(Button):
    def __init__(self, **kwargs):
        super().__init__(
            style_classes=["button-basic", "button-basic-props", "button-border"],
            **kwargs,
        )
        self.planel_icon_size = 20

        self.bluetooth_icon = Image(
            name="panel-icon",
            icon_name=config.bluetooth_icons_names["bluetooth"],
            icon_size=self.planel_icon_size,
        )

        config.bluetooth_client.bind(
            "enabled",
            "visible",
            self.bluetooth_icon,
        )

        self.audio_icon = Image(name="panel-icon")
        config.audio.connect("speaker-changed", self.update_audio)

        self.network_icon = Image(name="panel-icon", icon_size=self.planel_icon_size)
        self._network_icon_binding: GObject.Binding | None = None

        def get_network_icon(*_):
            # follow whichever device is primary, and re-run when that changes
            if self._network_icon_binding is not None:
                self._network_icon_binding.unbind()
                self._network_icon_binding = None

            device = (
                config.network.get_wifi()
                if config.network.get_primary() == an.Primary.WIFI
                else config.network.get_wired()
            )
            if device is None:
                return
            self.network_icon.set_from_icon_name(
                device.get_icon_name(), self.planel_icon_size
            )
            self._network_icon_binding = device.bind_property(
                "icon-name", self.network_icon, "icon-name"
            )

        config.network.connect("notify::primary", get_network_icon)
        get_network_icon()

        self.add(
            Box(children=[self.network_icon, self.bluetooth_icon, self.audio_icon])
        )
        self.connect("clicked", self.on_click)

        QuickSettingsPopup.reveal_child.revealer.connect(
            "notify::reveal-child",
            lambda *args: (
                [
                    self.add_style_class("button-basic-active"),
                    self.remove_style_class("button-basic"),
                ]
                if QuickSettingsPopup.popup_visible
                else [
                    self.remove_style_class("button-basic-active"),
                    self.add_style_class("button-basic"),
                ]
            ),
        )

    def update_audio(self, *args):
        self.audio_icon.set_from_icon_name(
            config.audio_icon_name(config.audio.speaker), self.planel_icon_size
        )

    def on_click(self, *args):
        QuickSettingsPopup.toggle_popup()


QuickSettingsPopup = PopupWindow(
    transition_duration=400,
    anchor="top-right",
    transition_type="slide-down",
    child=QuickSettings(),
    enable_inhibitor=True,
)
