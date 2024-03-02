import fabric
from bluetooth import BluetoothDevice,BluetoothClient
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.widgets.button import Button
from fabric.widgets.wayland import Window
from fabric.utils import invoke_repeater


class BtDeviceBox(Box):
    def __init__(self, device:BluetoothDevice,**kwargs):
        super().__init__(
            spacing=2,
            **kwargs
        )
        self.device = device
        self.device.connect("closed", lambda _: self.destroy())

        self.connect_button = Button(label="")
        self.connect_button.set_label("connected") if self.device.connected else self.connect_button.set_label("disconnected")
        self.connect_button.connect("clicked", lambda _: self.device.set_connection(not self.device.connected))
        self.device.connect("notify::connecting", lambda _, __: self.connect_button.set_label("connecting...") if not self.device.connected else self.connect_button.set_label("connected"))
        self.device.connect("notify::connected", lambda _, __: self.connect_button.set_label("connected") if self.device.connected else self.connect_button.set_label("disconnected"))


        self.add(Image(icon_name=device.icon + "-symbolic", icon_size=6))
        self.add(Label(label=device.name))
        self.add(self.connect_button)



class BtConnectionsList(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="vertical",
            spacing=5,
            **kwargs
        )

        self.client = BluetoothClient()
        self.client.connect("device-added",self.new_device)
        self.scan_button = Button(label="scan")
        self.scan_button.connect("clicked", lambda _: self.client.scan_devices())
        self.add(self.scan_button)

    def new_device(self, client: BluetoothClient, address):
        device: BluetoothDevice = client.get_device_from_addr(address)
        self.add_children(BtDeviceBox(device))

class BluetoothWidget(Window):
    def __init__(self, **kwargs):
        super().__init__(
            layer="top",
            anchor="top left",
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
    bt  = BluetoothWidget()
    fabric.start()