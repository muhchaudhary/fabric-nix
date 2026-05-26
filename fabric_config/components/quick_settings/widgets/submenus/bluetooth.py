from fabric_config.components.quick_settings.widgets.quick_settings_submenu import (
    QuickSubMenu,
    QuickSubToggle,
)
from fabric_config.widgets.toggle_pill import TogglePill
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.bluetooth.service import BluetoothClient, BluetoothDevice


class BluetoothDeviceBox(CenterBox):
    def __init__(self, device: BluetoothDevice, **kwargs):
        super().__init__(h_expand=True, name="submenu-row", **kwargs)
        self.device: BluetoothDevice = device

        self.pill = TogglePill(
            on_label="Connected",
            off_label="Connect",
            active=device.connected,
            on_toggled=self._on_pill_toggled,
        )

        self.device.connect("notify::connecting", self._on_connecting)
        self.device.connect("notify::connected", self._on_connected)

        self.add_start(
            Box(
                spacing=10,
                v_align="center",
                children=[
                    Image(
                        icon_name=device.icon_name + "-symbolic",
                        icon_size=16,
                        name="submenu-row-icon",
                    ),
                    Label(label=device.name, name="submenu-row-label", ellipsize="end"),
                ],
            )
        )
        self.add_end(self.pill)

    def _on_pill_toggled(self, active: bool):
        self.device.set_property("connecting", active)

    def _on_connecting(self, device, _):
        if self.device.connecting:
            self.pill._label.set_label("Connecting…")
            self.pill.add_style_class("loading")

    def _on_connected(self, *args):
        self.pill.remove_style_class("loading")
        self.pill.set_active(self.device.connected)


class BluetoothSubMenu(QuickSubMenu):
    def __init__(self, client: BluetoothClient, **kwargs):
        self.client = client
        self.client.connect("device-added", self.populate_new_device)

        self.paired_devices = Box(
            orientation="v",
            spacing=2,
            h_expand=True,
            children=[
                Label(
                    label="PAIRED DEVICES",
                    name="submenu-section-header",
                    h_align="start",
                )
            ],
        )

        self.available_devices = Box(
            orientation="v",
            spacing=2,
            h_expand=True,
            children=[
                Label(
                    label="AVAILABLE DEVICES",
                    name="submenu-section-header",
                    h_align="start",
                )
            ],
        )

        for device in self.client.devices:
            if device.paired:
                self.paired_devices.add(BluetoothDeviceBox(device))

        self.scan_button = Button(
            image=Image(icon_name="view-refresh-symbolic", icon_size=14),
            name="submenu-title-action",
            tooltip_text="Scan for devices",
        )
        self.scan_button.connect("clicked", self.on_scan_toggle)

        scroll_content = Box(
            orientation="v",
            spacing=8,
            children=[self.paired_devices, self.available_devices],
        )

        self.child = ScrolledWindow(
            min_content_size=(-1, 260),
            max_content_size=(-1, 260),
            propagate_width=True,
            child=scroll_content,
        )

        super().__init__(
            title="Bluetooth",
            title_icon="bluetooth-active-symbolic",
            title_action=self.scan_button,
            child=self.child,
            **kwargs,
        )

    def on_scan_toggle(self, btn: Button):
        self.client.toggle_scan()
        if self.client.scanning:
            btn.add_style_class("active")
        else:
            btn.remove_style_class("active")

    def populate_new_device(self, client: BluetoothClient, address: str):
        device = client.get_device(address)
        if device is None:
            return
        box = BluetoothDeviceBox(device)
        if device.paired:
            self.paired_devices.add(box)
        else:
            self.available_devices.add(box)


class BluetoothToggle(QuickSubToggle):
    def __init__(self, submenu: QuickSubMenu, client: BluetoothClient, **kwargs):
        super().__init__(
            action_label="Not Connected",
            action_icon="bluetooth-active-symbolic",
            submenu=submenu,
            **kwargs,
        )
        self.client = client
        self.client.connect("notify::enabled", self.toggle_bluetooth)
        self.client.connect("device-added", self.new_device)

        self.toggle_bluetooth(client)

        for device in self.client.devices:
            self.new_device(client, device.address)
        self.device_connected(
            self.client.connected_devices[0]
        ) if self.client.connected_devices else None

        self.connect("action-clicked", lambda *_: self.client.toggle_power())

    def toggle_bluetooth(self, client: BluetoothClient, *_):
        if client.enabled:
            self.set_active_style(True)
            self.action_icon.set_from_icon_name("bluetooth-active-symbolic", 20)
            self.action_label.set_label("Not Connected")
        else:
            self.set_active_style(False)
            self.action_icon.set_from_icon_name("bluetooth-disabled-symbolic", 20)
            self.action_label.set_label("Disabled")

    def new_device(self, client: BluetoothClient, address):
        device = client.get_device(address)
        if device is not None:
            device.connect("changed", self.device_connected)

    def device_connected(self, device: BluetoothDevice):
        if device.connected:
            self.action_label.set_label(device.name)
        elif self.action_label.get_label() == device.name:
            self.action_label.set_label(
                self.client.connected_devices[0].name
                if self.client.connected_devices
                else "Not Connected"
            )
