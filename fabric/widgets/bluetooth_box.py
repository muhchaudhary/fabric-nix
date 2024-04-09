from fabric.bluetooth.service import BluetoothClient, BluetoothDevice
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer

bluetooth_icons = {
    "bluetooth": "󰂯",
    "bluetooth-off": "󰂲",
    "menu-right": "󰍟",
    "menu-down": "󰍝",
    "scan": "󰁪",
}


class BtDeviceBox(CenterBox):
    def __init__(self, device: BluetoothDevice, **kwargs):
        super().__init__(spacing=2, name="submenu-item", h_expand=True, **kwargs)
        self.device = device
        self.device.connect("closed", lambda _: self.destroy())

        self.connect_button = Button(name="submenu-button")
        self.connect_button.connect(
            "clicked", lambda _: self.device.set_connection(not self.device.connected)
        )
        self.device.connect("connecting", self.on_device_connecting)
        self.device.connect("notify::connected", self.on_device_connect)

        self.add_start(
            Image(icon_name=device.icon + "-symbolic", icon_size=5, name="submenu-icon")
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
            "connected"
        ) if self.device.connected else self.connect_button.set_label("disconnected")


class BluetoothReveal(Revealer):
    def __init__(self, client: BluetoothClient, **kwargs):
        super().__init__(
            h_expand=True, transition_duration=100, transition_type="slide-down"
        )
        self.client: BluetoothClient = client
        # Scan Button
        self.scan_button = Button(label=bluetooth_icons["scan"], name="submenu-button")
        self.scan_button.connect("clicked", lambda _: self.client.toggle_scan())

        self.paired_box = Box(orientation="vertical", h_expand=True)
        self.available_box = Box(orientation="vertical", h_expand=True)


        self.box_child = Box(
            orientation="v",
            h_expand=True,
            name="submenu",
            children=[
                CenterBox(
                    h_expand=True,
                    name="submenu-title",
                    start_children=Label(
                        name="submenu-title-label",
                        label=bluetooth_icons["bluetooth"] + " Bluetooth",
                    ),
                    end_children=self.scan_button,
                ),
                self.paired_box,
                CenterBox(
                    start_children=Label("Available Devices"),
                ),
                self.available_box,
            ],
        )

    def new_device(self, client: BluetoothClient, address):
        device: BluetoothDevice = client.get_device_from_addr(address)
        if device.paired:
            self.paired_box.add(BtDeviceBox(device))
        else:
            self.available_box.add(BtDeviceBox(device))



class BluetoothToggle(Box):
    def __init__(self, client: BluetoothClient, **kwargs):
        super().__init__(
            spacing=2,
            orientation="vertical",
            h_expand=True,
            **kwargs,
        )
        self.client = client

        # Scan Button
        self.scan_button = Button(label=bluetooth_icons["scan"], name="submenu-button")
        self.scan_button.connect("clicked", lambda _: self.client.toggle_scan())


        # Boxes to hold the devices
        self.paired_box = Box(orientation="vertical", h_expand=True)
        self.available_box = Box(orientation="vertical", h_expand=True)

        # Bluetooth Button
        self.bluetooth_toggle = Button(name="quicksettings-toggle")
        self.bluetooth_toggle_icon = Image(
            name="panel-icon", icon_name="bluetooth-active-symbolic", pixel_size=16
        )
        self.bluetooth_toggle_name = Label(name="panel-text", label="Not Connected")
        self.bluetooth_toggle_children = Box(
            name="bluetooth-icon-label",
            v_align="center",
            h_align="start",
            children=[self.bluetooth_toggle_icon, self.bluetooth_toggle_name],
        )
        self.bluetooth_toggle.add(self.bluetooth_toggle_children)

        self.bluetooth_toggle.connect(
            "clicked", lambda *args: self.client.toggle_power()
        )
        self.client.connect("notify::enabled", self.toggle_bluetooth)

        # Reveal button
        self.reveal_button = Button(
            name="quicksettings-revealer", label=bluetooth_icons["menu-right"]
        )
        self.reveal_button.connect("clicked", self.toggle_reveal)
        self.bt_buttons = Box(
            name="quicksettings-option",
            h_align="start",
            v_align="start",
            children=[self.bluetooth_toggle, self.reveal_button],
        )

        # Revealer
        self.revealer = Revealer(
            h_expand=True,
            children=Box(
                orientation="v",
                # h_align="start",
                h_expand=True,
                name="submenu",
                children=[
                    CenterBox(
                        h_expand=True,
                        name="submenu-title",
                        start_children=Label(
                            name="submenu-title-label",
                            label=bluetooth_icons["bluetooth"] + " Bluetooth",
                        ),
                        end_children=self.scan_button,
                    ),
                    self.paired_box,
                    CenterBox(
                        start_children=Label("Available Devices"),
                    ),
                    self.available_box,
                ],
            ),
            transition_duration=100,
            transition_type="slide-down",
        )

        # Client logic
        self.client.connect("device-added", self.new_device)
        self.client.connect(
            "notify::scanning",
            lambda *args: self.scan_button.set_style("background-color:red")
            if self.client.scanning
            else self.scan_button.set_style(""),
        )

        # Self
        self.add(self.bt_buttons)
        self.add(self.revealer)

    def toggle_reveal(self, *args):
        reveal_status = not self.revealer.get_reveal_child()
        self.revealer.set_reveal_child(reveal_status)
        if reveal_status:
            self.reveal_button.set_label(bluetooth_icons["menu-down"])
        else:
            self.reveal_button.set_label(bluetooth_icons["menu-right"])

    def toggle_bluetooth(self, *args):
        if self.client.enabled:
            self.bluetooth_toggle_icon.set_from_icon_name(
                "bluetooth-active-symbolic", 1
            )
            self.bluetooth_toggle_name.set_label("Not Connected")
            self.bluetooth_toggle.set_name("quicksettings-toggle-active")
            self.reveal_button.set_name("quicksettings-revealer-active")
        else:
            self.bluetooth_toggle_icon.set_from_icon_name(
                "bluetooth-disabled-symbolic", 1
            )
            self.bluetooth_toggle_name.set_label("Disabled")
            self.bluetooth_toggle.set_name("quicksettings-toggle")
            self.reveal_button.set_name("quicksettings-revealer")
        self.bluetooth_toggle_icon.set_pixel_size(16)

    def new_device(self, client: BluetoothClient, address):
        device: BluetoothDevice = client.get_device_from_addr(address)
        device.connect("notify::connected", self.device_connected)
        if device.paired:
            self.paired_box.add(BtDeviceBox(device))
        else:
            self.available_box.add(BtDeviceBox(device))

    def device_connected(self, device: BluetoothDevice, _):
        connection = device.connected
        if connection:
            self.bluetooth_toggle_name.set_label(device.name)
        else:
            if self.bluetooth_toggle_name.get_label() == device.name:
                connected_devices = self.client.connected_devices
                if connected_devices:
                    self.bluetooth_toggle_name.set_label(connected_devices[0].name)
                else:
                    self.bluetooth_toggle_name.set_label("Not Connected")
