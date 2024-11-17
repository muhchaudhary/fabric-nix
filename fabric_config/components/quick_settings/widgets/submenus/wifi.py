from fabric_config.components.quick_settings.widgets.quick_settings_submenu import (
    QuickSubMenu,
    QuickSubToggle,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.widgets.scrolledwindow import ScrolledWindow

from fabric_config.services.wifi import NetworkClient, Wifi


class WifiSubMenu(QuickSubMenu):
    def __init__(self, client: NetworkClient, **kwargs):
        self.client = client
        self.wifi_device = self.client.wifi_device
        self.client.connect("device-ready", self.on_device_ready)

        self.available_networks_box = Box(orientation="v", spacing=4, h_expand=True)

        self.scan_button = Button(label="Scan", name="panel-button")
        self.scan_button.connect("clicked", self.start_new_scan)

        self.child = ScrolledWindow(
            min_content_size=(-1, 100),
            max_content_size=(-1, 100),
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

    def start_new_scan(self, _):
        self.client.wifi_device.scan() if self.client.wifi_device else None
        self.build_wifi_options()

    def on_device_ready(self, client: NetworkClient):
        self.wifi_device = client.wifi_device
        self.build_wifi_options()

    def build_wifi_options(self):
        self.available_networks_box.children = []
        if not self.wifi_device:
            return
        for ap in self.wifi_device.access_points:
            if ap.get("ssid") != "Unknown":
                btn = self.make_button_from_ap(ap)
                self.available_networks_box.add(btn)

    def make_button_from_ap(self, ap) -> Button:
        ap_button = Button(name="panel-button")
        ap_button.add(
            Box(
                children=[
                    Image(icon_name=ap.get("icon-name"), icon_size=24),
                    Label(label=ap.get("ssid")),
                ]
            )
        )
        ap_button.connect(
            "clicked", lambda _: self.client.connect_wifi_bssid(ap.get("bssid"))
        )
        return ap_button


class WifiToggle(QuickSubToggle):
    def __init__(self, submenu: QuickSubMenu, client: NetworkClient, **kwargs):
        super().__init__(submenu=submenu, **kwargs)
        self.client = client
        self.client.connect("device-ready", self.update_action_button)

        self.connect("action-clicked", self.on_action)

    def update_action_button(self, client: NetworkClient):
        wifi = client.wifi_device
        if wifi:
            wifi.connect(
                "notify::enabled",
                lambda *args: self.set_active_style(wifi.get_property("enabled")),  # type: ignore
            )

            self.action_icon.set_from_icon_name(wifi.get_property("icon-name") +"-symbolic", 24)
            wifi.bind_property("icon-name", self.action_icon, "icon-name")

            self.action_label.set_label(wifi.get_property("ssid"))
            wifi.bind_property("ssid", self.action_label, "label")

    def on_action(self, btn):
        wifi: Wifi | None = self.client.wifi_device
        if wifi:
            wifi.toggle_wifi()
