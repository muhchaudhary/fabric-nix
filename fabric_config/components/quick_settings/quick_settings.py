import gi
from fabric.widgets.box import Box
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
    WifiSubMenu,
    WifiToggle,
)
from fabric_config.widgets.player import PlayerBoxStack
from fabric_config.widgets.popup_window_v2 import PopupWindow
from fabric_config.components.quick_settings.widgets.buttons.theme_toggle import (
    ThemeToggle,
)

gi.require_version("AstalNetwork", "0.1")
from gi.repository import AstalNetwork as an  # noqa: E402
from gi.repository import GObject  # noqa: E402


class QuickSettingsButtonBox(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="v",
            spacing=4,
            **kwargs,
        )
        self.buttons = Box(
            orientation="h",
            spacing=4,
            v_align="center",
            homogeneous=True,  # Ensures items are the same width
        )
        self.active_submenu = None

        # Wifi
        self.wifi_toggle = WifiToggle(
            submenu=WifiSubMenu(config.network),
            client=config.network,
        )

        # Bluetooth
        self.bluetooth_toggle = BluetoothToggle(
            submenu=BluetoothSubMenu(config.bluetooth_client),
            client=config.bluetooth_client,
        )

        self.buttons.pack_start(self.wifi_toggle, True, True, 0)
        self.buttons.pack_start(self.bluetooth_toggle, True, True, 0)

        self.wifi_toggle.connect("reveal-clicked", self.set_active_submenu)
        self.bluetooth_toggle.connect("reveal-clicked", self.set_active_submenu)

        self.add(self.buttons)
        self.add(self.wifi_toggle.submenu)
        self.add(self.bluetooth_toggle.submenu)

    def set_active_submenu(self, btn: QuickSubToggle):
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
        self.theme_toggle = ThemeToggle()

        self.add(self.buttons_box)
        self.add(self.theme_toggle)
        self.add(self.audio_slider_box)
        self.add(self.screen_bright_slider)
        self.add(self.mprisBox)


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
