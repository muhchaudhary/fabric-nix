import fabric_config.config as config

from fabric_config.components.quick_settings.widgets.quick_settings_submenu import (
    QuickSubToggle,
)

from fabric_config.components.quick_settings.widgets.submenus import (
    BluetoothSubMenu,
    BluetoothToggle,
    WifiSubMenu,
    WifiToggle,
)
from fabric_config.components.quick_settings.widgets.sliders import (
    AudioSlider,
    BrightnessSlider,
)

from fabric_config.widgets.player import PlayerBoxStack
from fabric_config.widgets.popup_window_v2 import PopupWindow

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image


class QuickSettingsButtonBox(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="v",
            spacing=4,
            h_align="start",
            v_align="start",
            h_expand=True,
            v_expand=True,
            **kwargs,
        )
        self.buttons = Box(
            orientation="h", spacing=4, h_align="center", v_align="center"
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

        self.buttons.add(self.wifi_toggle)
        self.buttons.add(self.bluetooth_toggle)

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
            style_classes=["cool-border"],
            name="quicksettings",
            **kwargs,
        )
        self.mprisBox = PlayerBoxStack(config.mprisplayer)
        self.screen_bright_slider = BrightnessSlider(config.brightness)
        self.audio_slider_box = AudioSlider(config.audio)
        self.buttons_box = QuickSettingsButtonBox()

        self.add(self.buttons_box)
        self.add(self.audio_slider_box)
        self.add(self.screen_bright_slider)
        self.add(self.mprisBox)


class QuickSettingsButton(Button):
    def __init__(self, **kwargs):
        super().__init__(style_classes=["button-basic", "button-basic-props", "button-border"], **kwargs)
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

        def get_network_icon(*_):
            if config.network.primary_device == "wifi":
                wifi = config.network.wifi_device
                if wifi:
                    self.network_icon.set_from_icon_name(
                        wifi.get_icon_name(), self.planel_icon_size
                    )
                    # wifi.bind_property("icon-name", self.network_icon, "icon-name")

            else:
                ethernet = config.network.ethernet_device
                if ethernet:
                    self.network_icon.set_from_icon_name(
                        ethernet.get_icon_name(), self.planel_icon_size
                    )

        self.network_icon = Image(name="panel-icon", icon_size=self.planel_icon_size)
        # config.network.connect("device-ready", get_network_icon)

        config.network.connect("notify::primary-device", get_network_icon)

        self.add(
            Box(children=[self.network_icon, self.bluetooth_icon, self.audio_icon])
        )
        self.connect("clicked", self.on_click)

        QuickSettingsPopup.reveal_child.revealer.connect(
            "notify::reveal-child",
            lambda *args: [
                self.add_style_class("button-basic-active"),
                self.remove_style_class("button-basic"),
            ]
            if QuickSettingsPopup.popup_visible
            else [
                self.remove_style_class("button-basic-active"),
                self.add_style_class("button-basic"),
            ],
        )

    def update_audio(self, *args):
        vol = config.audio.speaker.volume
        if config.audio.speaker.muted:
            self.audio_icon.set_from_icon_name(
                config.audio_icons_names["mute"], self.planel_icon_size
            )
            return
        if vol >= 66:
            self.audio_icon.set_from_icon_name(
                config.audio_icons_names["high"], self.planel_icon_size
            )
        elif 33 <= vol < 66:
            self.audio_icon.set_from_icon_name(
                config.audio_icons_names["medium"], self.planel_icon_size
            )
        elif 0 < vol < 33:
            self.audio_icon.set_from_icon_name(
                config.audio_icons_names["low"], self.planel_icon_size
            )
        else:
            self.audio_icon.set_from_icon_name(
                config.audio_icons_names["off"], self.planel_icon_size
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
