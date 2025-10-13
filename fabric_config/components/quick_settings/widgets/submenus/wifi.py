import gi
from fabric_config.components.quick_settings.widgets.quick_settings_submenu import (
    QuickSubMenu,
    QuickSubToggle,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.widgets.scrolledwindow import ScrolledWindow

gi.require_version("AstalNetwork", "0.1")
from gi.repository import AstalNetwork as an


class WifiSubMenu(QuickSubMenu):
    def __init__(self, network: an.Network, **kwargs):
        self.network = network
        self.wifi_device = self.network.get_wifi()
        if isinstance(self.wifi_device, an.Wifi):
            self.wifi_device.connect(
                "notify::scanning", lambda *_: self.build_wifi_options()
            )

        self.available_networks_box = Box(orientation="v", spacing=4, h_expand=True)
        self.seen_networks = set()

        self.scan_button = Button(label="Scan", name="panel-button")
        self.scan_button.connect(
            "clicked", lambda *_: self.wifi_device.scan() if self.wifi_device else None
        )

        self.child = ScrolledWindow(
            min_content_size=(-1, 300),
            max_content_size=(-1, 300),
            propagate_width=True,
            propagate_height=True,
            child=self.available_networks_box,
        )

        super().__init__(
            title="Network",
            title_icon="network-wireless-symbolic",
            child=Box(orientation="v", children=[self.scan_button, self.child]),
            **kwargs,
        )

    def build_wifi_options(self):
        if self.wifi_device.get_scanning():
            self.available_networks_box.children = []
            self.seen_networks.clear()
            if not isinstance(self.wifi_device, an.Wifi):
                return
            for ap in self.wifi_device.get_access_points():
                ap: an.AccessPoint = ap
                if ap.get_ssid() and ap.get_ssid() not in self.seen_networks:
                    self.seen_networks.add(ap.get_ssid())
                    btn = self.make_button_from_ap(ap)
                    self.available_networks_box.add(btn)

    def make_button_from_ap(self, ap: an.AccessPoint) -> Button:
        ap_button = Button(name="panel-button")
        ap_button.add(
            Box(
                children=[
                    Image(icon_name=ap.get_icon_name(), icon_size=24),
                    Label(label=ap.get_ssid()),
                ]
            )
        )
        ap_button.connect(
            "clicked",
            lambda _: self.network.get_client().connect_wifi_bssid(ap.get_bssid()),
        )
        return ap_button


class WifiToggle(QuickSubToggle):
    def __init__(self, submenu: QuickSubMenu, client: an.Network, **kwargs):
        super().__init__(
            action_icon="network-wireless-disabled-symbolic",
            action_label=" Wifi Disabled",
            submenu=submenu,
            **kwargs,
        )
        self.client = client
        self.update_action_button()

        self.connect("action-clicked", self.on_action)

    def update_action_button(self):
        wifi = self.client.get_wifi()
        if wifi:
            self.action_icon.set_from_icon_name(wifi.get_icon_name() + "-symbolic", 24)
            self.action_label.set_label(wifi.get_ssid())
            self.set_active_style(wifi.get_enabled())

            wifi.connect(
                "notify::enabled",
                lambda *args: [
                    self.set_active_style(wifi.get_enabled()),
                    self.action_label.set_label("Wifi Disabled")
                    if not wifi.get_enabled()
                    else self.action_label.set_label(wifi.get_ssid()),
                ],  # type: ignore
            )

            wifi.bind("icon-name", "icon-name", self.action_icon)
            wifi.bind("ssid", "label", self.action_label)

    def on_action(self, btn):
        wifi: an.Wifi | None = self.client.get_wifi()
        if wifi:
            wifi.set_enabled(not wifi.get_enabled())
