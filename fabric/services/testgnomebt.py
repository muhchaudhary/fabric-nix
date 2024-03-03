import fabric
from bluetooth import BluetoothDevice, BluetoothClient
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.widgets.button import Button
from fabric.widgets.wayland import Window

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class BtDeviceBox(Box):
    def __init__(self, device: BluetoothDevice, **kwargs):
        super().__init__(spacing=2, **kwargs)
        self.device = device
        self.device.connect("closed", lambda _: self.destroy())

        self.connect_button = Button()
        self.connect_button.set_label(
            "connected"
        ) if self.device.connected else self.connect_button.set_label("disconnected")
        self.connect_button.connect(
            "clicked", lambda _: self.device.set_connection(not self.device.connected)
        )
        self.device.connect("notify::connecting", self.on_device_connecting)
        self.device.connect("notify::connected", self.on_device_connect)

        self.add(Image(icon_name=device.icon, icon_size=6))
        self.add(Label(label=device.name))
        self.add(self.connect_button)

    def on_device_connecting(self, *args):
        self.connect_button.set_label(
            "connecting..."
        ) if not self.device.connected else self.connect_button.set_label("connected")

    def on_device_connect(self, *args):
        self.connect_button.set_label(
            "connected"
        ) if self.device.connected else self.connect_button.set_label("disconnected")


class BtConnectionsList(Box):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", spacing=5, **kwargs)

        self.client = BluetoothClient()
        self.client.connect("device-added", self.new_device)
        self.scan_button = Button(label="scan")
        self.scan_button.connect("clicked", lambda _: self.client.toggle_scan())
        self.client.connect(
            "notify::scanning",
            lambda *args: self.scan_button.set_label("stop")
            if self.client.scanning
            else self.scan_button.set_label("scan"),
        )
        self.toggle_button = Button()
        self.toggle_button.set_label(
            "bt on"
        ) if self.client.enabled else self.toggle_button.set_label("bt off")
        self.toggle_button.connect("clicked", lambda _: self.client.toggle_power())
        self.client.connect(
            "notify::enabled",
            lambda *args: self.toggle_button.set_label("bt on")
            if self.client.enabled
            else self.toggle_button.set_label("bt off"),
        )

        self.paired_box = Box(orientation="vertical", children=Label("Paired Devices"))
        self.available_devices = Box(
            orientation="vertical", children=Label("Available Devices")
        )
        self.add(Box(children=[self.scan_button, self.toggle_button]))
        self.add(self.paired_box)
        self.add(self.available_devices)

    def new_device(self, client: BluetoothClient, address):
        device: BluetoothDevice = client.get_device_from_addr(address)
        if device.paired:
            self.paired_box.add(BtDeviceBox(device))
        else:
            self.available_devices.add(BtDeviceBox(device))


class BluetoothWidget(Window):
    def __init__(self, **kwargs):
        super().__init__(
            layer="top",
            anchor="top right",
            margin="0px 0px 0px 0px",
            all_visible=True,
            exclusive=True,
        )
        self.btbox = BtConnectionsList()
        self.widgets_container = Box(
            spacing=2,
            orientation="v",
            name="widgets-container",
        )
        self.widgets_container.add(self.btbox)
        self.add(self.widgets_container)
        self.show_all()


if __name__ == "__main__":
    bt = BluetoothWidget()
    fabric.start()
