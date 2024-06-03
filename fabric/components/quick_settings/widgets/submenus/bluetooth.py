from components.quick_settings.widgets.quick_settings_submenu import (
    QuickSubMenu,
    QuickSubToggle,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.widgets.scrolled_window import ScrolledWindow
from fabric.bluetooth.service import BluetoothClient, BluetoothDevice


class BluetoothDeviceBox(CenterBox):
    def __init__(self, device: BluetoothDevice, **kwargs):
        # TODO: FIX STYLING, make it look better
        super().__init__(spacing=2, name="panel-button", h_expand=True, **kwargs)
        self.device = device
        self.device.connect("closed", lambda _: self.destroy())

        self.connect_button = Button(name="panel-button")
        self.connect_button.connect(
            "clicked",
            lambda _: self.device.set_connection(not self.device.connected),
        )
        self.device.connect("connecting", self.on_device_connecting)
        self.device.connect("notify::connected", self.on_device_connect)

        self.add_start(
            Image(
                icon_name=device.icon + "-symbolic", icon_size=2, name="submenu-icon"
            ),
        )  # type: ignore
        self.add_start(Label(label=device.name, name="submenu-label"))  # type: ignore
        self.add_end(self.connect_button)

    def on_device_connecting(self, device: BluetoothDevice, connecting):
        if connecting:
            self.connect_button.set_label("connecting...")
        elif device.connected:
            self.connect_button.set_label("connected")
        else:
            self.connect_button.set_label("failed to connect")

    def on_device_connect(self, *args):
        self.connect_button.set_label(
            "connected",
        ) if self.device.connected else self.connect_button.set_label("disconnected")


class BluetoothSubMenu(QuickSubMenu):
    def __init__(self, client: BluetoothClient, **kwargs):
        self.client = client
        self.client.connect("device-added", self.populate_new_device)

        self.paired_devices = Box(
            orientation="v",
            spacing=4,
            h_expand=True,
            children=Label("Paired Devices", h_align="start"),
        )
        self.available_devices = Box(
            orientation="v",
            spacing=4,
            h_expand=True,
            children=Label("Available Devices", h_align="start"),
        )

        self.scan_image = Image(
            icon_name="view-refresh-symbolic", icon_size=1, pixel_size=20
        )
        self.scan_button = Button(icon_image=self.scan_image, name="panel-button")
        self.scan_button.connect("clicked", self.on_scan_toggle)

        self.child = ScrolledWindow(
            min_content_height=200,
            propagate_natural_width=True,
            children=Box(
                orientation="v",
                children=Box(
                    orientation="v",
                    children=[self.paired_devices, self.available_devices],
                ),
            ),
        )

        super().__init__(
            title="Bluetooth",
            title_icon="bluetooth-active-symbolic",
            child=Box(orientation="v", children=[self.scan_button, self.child]),
            **kwargs,
        )

    def on_scan_toggle(self, btn: Button):
        self.client.toggle_scan()
        btn.set_style_classes(
            ["active"]
        ) if self.client.scanning else btn.set_style_classes([""])

    def populate_new_device(self, client: BluetoothClient, address: str):
        device: BluetoothDevice = client.get_device_from_addr(address)
        # device.connect("notify:connected", self.on_device_connect)
        if device.paired:
            self.paired_devices.add(BluetoothDeviceBox(device))
        else:
            self.available_devices.add(BluetoothDeviceBox(device))


class BluetoothToggle(QuickSubToggle):
    def __init__(self, submenu: QuickSubMenu, client: BluetoothClient, **kwargs):
        super().__init__(
            action_label="Not Connected",
            action_icon="bluetooth-active-symbolic",
            submenu=submenu,
            **kwargs,
        )
        # Client Signals
        self.client = client
        self.client.connect("notify::enabled", self.toggle_bluetooth)
        self.client.connect("device-added", self.new_device)

        # Button Signals
        self.connect("action-clicked", lambda *_: self.client.toggle_power())

    def toggle_bluetooth(self, client: BluetoothClient, *_):
        if client.enabled:
            self.set_active_style(True)
            self.action_icon.set_from_icon_name("bluetooth-active-symbolic", 1)
            self.action_label.set_label("Not Connected")
        else:
            self.set_active_style(False)
            self.action_icon.set_from_icon_name("bluetooth-disabled-symbolic", 1)
            self.action_label.set_label("Disabled")

    def new_device(self, client: BluetoothClient, address):
        device: BluetoothDevice = client.get_device_from_addr(address)
        device.connect("notify::connected", self.device_connected)

    def device_connected(self, device: BluetoothDevice, _):
        connection = device.connected
        if connection:
            self.action_label.set_label(device.name)
        elif self.action_label.get_label() == device.name:
            connected_devices = self.client.connected_devices
            if connected_devices:
                self.action_label.set_label(connected_devices[0].name)
            else:
                self.action_label.set_label("Not Connected")
