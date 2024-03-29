from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.revealer import Revealer
from fabric.bluetooth.service import BluetoothClient, BluetoothDevice
from fabric.widgets.scrolled_window import ScrolledWindow
from fabric.widgets.image import Image

bluetooth_icons = {
    "bluetooth": "󰂯",
    "bluetooth-off": "󰂲",
    "menu-right": "󰍟",
    "menu-down": "󰍝",
    "scan": "󰁪",
}


class BtDeviceBox(CenterBox):
    def __init__(self, device: BluetoothDevice, **kwargs):
        super().__init__(spacing=2, name="submenu-item", **kwargs)
        self.device = device
        self.device.connect("closed", lambda _: self.destroy())

        self.connect_button = Button(name="submenu-button")
        self.connect_button.connect(
            "clicked", lambda _: self.device.set_connection(not self.device.connected)
        )
        self.device.connect("connecting", self.on_device_connecting)
        self.device.connect("notify::connected", self.on_device_connect)

        self.add_left(Image(icon_name=device.icon + "-symbolic", icon_size=5, name="submenu-icon"))  # type: ignore
        self.add_left(Label(label=device.name, name="submenu-label"))  # type: ignore
        self.add_right(self.connect_button)

    def on_device_connecting(self, device:BluetoothDevice, connecting):
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


class BluetoothToggle(Box):
    def __init__(self, client: BluetoothClient, **kwargs):
        super().__init__(
            spacing=2, name="quicksettings-option", orientation="vertical", **kwargs
        )
        self.client = client

        # Boxes to hold the devices
        self.paired_box = Box(orientation="vertical")
        self.available_box = Box(orientation="vertical")

        # Scan Button
        self.scan_button = Button(label=bluetooth_icons["scan"], name="submenu-button")
        self.scan_button.connect("clicked", lambda _: self.client.toggle_scan())

        # Bluetooth Button
        self.bluetooth_toggle = Button(name="quicksettings-toggle")
        self.bluetooth_toggle_icon = Label(
            name="panel-icon", label=bluetooth_icons["bluetooth"]
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
        self.bt_buttons = Box(children=[self.bluetooth_toggle, self.reveal_button])

        # Revealer
        self.revealer = Revealer(
            children=Box(
                orientation="v",
                h_align="start",
                name="submenu",
                children=[
                    CenterBox(
                        name="submenu-title",
                        left_widgets=Label(
                            name="submenu-title-label",
                            label=bluetooth_icons["bluetooth"] + " Bluetooth",
                        ),
                        right_widgets=self.scan_button,
                    ),
                    self.paired_box,
                    CenterBox(
                        left_widgets=Label("Available Devices"),
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
            self.bluetooth_toggle_icon.set_label(bluetooth_icons["bluetooth"])
            self.bluetooth_toggle_name.set_label("Not Connected")
            self.bluetooth_toggle.set_name("quicksettings-toggle-active")
            self.reveal_button.set_name("quicksettings-revealer-active")
        else:
            self.bluetooth_toggle_icon.set_label(bluetooth_icons["bluetooth-off"])
            self.bluetooth_toggle_name.set_label("Disabled")
            self.bluetooth_toggle.set_name("quicksettings-toggle")
            self.reveal_button.set_name("quicksettings-revealer")

    def new_device(self, client: BluetoothClient, address):
        device: BluetoothDevice = client.get_device_from_addr(address)
        device.connect("notify::connected", self.device_connected)
        if device.paired:
            self.paired_box.add(BtDeviceBox(device))
        else:
            self.available_box.add(BtDeviceBox(device))

    def device_connected(self,device: BluetoothDevice,_):
        connection = device.connected
        print("CONNECTION:", connection)
        if connection:
            self.bluetooth_toggle_name.set_label(device.name)
        else:
            print(self.bluetooth_toggle_name.get_label())
            print(device.name)
            if self.bluetooth_toggle_name.get_label() == device.name:
                connected_devices = self.client.connected_devices
                if connected_devices:
                    self.bluetooth_toggle_name.set_label(connected_devices[0].name)
                else:
                    self.bluetooth_toggle_name.set_label("Not Connected")
