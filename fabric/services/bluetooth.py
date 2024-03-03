import gi
from loguru import logger
from fabric.service import Service, Signal, SignalContainer, Property
from fabric.utils import bulk_connect
from gi.repository import Gio, GLib
from fabric.utils import invoke_repeater


class GnomeBluetoothImportError(ImportError):
    def __init__(self, *args):
        super().__init__(
            "gnome-bluetooth is not installed, please install it first",
            *args,
        )


try:
    gi.require_version("GnomeBluetooth", "3.0")
    from gi.repository import GnomeBluetooth
except ValueError:
    raise GnomeBluetoothImportError()


# Declare for later
class BluetoothClient:
    pass


class BluetoothDevice(Service):
    __gsignals__ = SignalContainer(
        Signal("changed", "run-first", None, ()),
        Signal("closed", "run-first", None, ()),
    )

    def __init__(
        self, device: GnomeBluetooth.Device, client: BluetoothClient, **kwargs
    ):
        self._device: GnomeBluetooth.Device = device
        self._client = client
        self._signal_connectors: dict = {}
        for sn in [
            "battery-percentage",
            "battery-level",
            "connected",
            "trusted",
            "address",
            "paired",
            "alias",
            "icon",
            "name",
        ]:
            self._signal_connectors[sn] = self._device.connect(
                f"notify::{sn}", lambda *args, sn=sn: self.notifier(sn, args)
            )
        super().__init__(**kwargs)

    @Property(value_type=GnomeBluetooth.Device, flags="read")
    def device(self) -> GnomeBluetooth.Device:
        return self._device

    @Property(value_type=str, flags="read")
    def address(self) -> str:
        return self._device.props.address

    @Property(value_type=str, flags="read")
    def alias(self) -> str:
        return self._device.props.alias

    @Property(value_type=str, flags="read")
    def name(self) -> str:
        return self._device.props.name

    @Property(value_type=str, flags="read")
    def icon(self) -> str:
        return self._device.props.icon

    @Property(value_type=str, flags="read")
    def type(self) -> str:
        return GnomeBluetooth.type_to_string(self._device.type)

    @Property(value_type=bool, default_value=False, flags="read")
    def paired(self) -> bool:
        return self._device.props.paired

    @Property(value_type=bool, default_value=False, flags="read")
    def trusted(self) -> bool:
        return self._device.props.trusted

    @Property(value_type=bool, default_value=False, flags="read")
    def connected(self) -> bool:
        return self._device.props.connected

    @Property(value_type=bool, default_value=False, flags="read-write")
    def connecting(self) -> bool:
        return self._connecting

    @connecting.setter
    def connecting(self, value: bool):
        self._connecting = value
        self.emit("changed")
        return

    @Property(value_type=int, flags="read")
    def battery_level(self) -> int:
        return self._device.props.battery_level

    @Property(value_type=float, flags="read")
    def battery_percentage(self) -> float:
        return self._device.props.battery_percentage

    def set_connection(self, connect: bool):
        def callback(value):
            if value is False:
                return
            self._connecting = False
            self.notify("connecting")

        self._connecting = True
        self.notify("connecting")
        self._client.connect_device(self._device, connect, callback)

    def notifier(self, name: str, args=None):
        self.notify(name)
        self.emit("changed")
        return

    def close(self):
        for id in self._signal_connectors.values():
            try:
                self._device.disconnect(id)
            except:
                pass
        self.emit("closed")

    # def __del__(self):
    #     # hacking into the guts of python's garbage collector
    #     return self.close()


class BluetoothClient(Service):
    __gsignals__ = SignalContainer(
        Signal("device-added", "run-first", None, (str,)),
        Signal("device-removed", "run-first", None, (str,)),
        Signal("changed", "run-first", None, ()),
        Signal("closed", "run-first", None, ()),
    )

    def __init__(self, **kwargs):
        self._client: GnomeBluetooth.Client = GnomeBluetooth.Client.new()
        self._devices: dict = {}
        self._connected_devices: dict = {}

        bulk_connect(
            self._client,
            {
                "device-added": self.on_device_added,
                "device-removed": self.on_device_removed,
                "notify::default-adapter-state": lambda *args: self.notifier("state"),
                "notify::default-adapter-powered": lambda *args: self.notifier(
                    "enabled"
                ),
                "notify::default-adapter-setup-mode": lambda *args: self.notifier(
                    "scanning"
                ),
            },
        )
        for device in self._get_devices():
            self.on_device_added(self._client, device)
        super().__init__(**kwargs)

    def toggle_power(self):
        GLib.idle_add(
            lambda: self._client.set_property(
                "default_adapter_powered",
                not self._client.props.default_adapter_powered,
            )
        )

    def toggle_scan(self):
        GLib.idle_add(
            lambda: self._client.set_property(
                "default_adapter_setup_mode",
                not self._client.props.default_adapter_setup_mode,
            )
        )

    def _get_devices(self):
        devices = []
        device_store = self._client.get_devices()
        for i in range(device_store.get_n_items()):
            device = device_store.get_item(i)
            if device.paired or device.trusted:
                devices.append(device)
        return devices

    def on_device_added(
        self, client: GnomeBluetooth.Client, device: GnomeBluetooth.Device
    ):
        if device.props.address in self._devices.keys():
            return
        if device.props.name is None:
            return
        bluetooth_device = BluetoothDevice(device, self)
        bluetooth_device.connect("changed", lambda _: self.emit("changed"))
        bluetooth_device.connect(
            "notify::connected", lambda _, __: self.notify("connected-devices")
        )
        self._devices[device.props.address] = bluetooth_device
        self.notifier("devices")
        self.emit("device-added", device.props.address)

    def on_device_removed(self, client: GnomeBluetooth.Client, object_path: str):
        # TODO may not be a reliable method of obtaining the address
        # object path is of the form /org/bluez/hci0/dev_AA_AA_AA_AA_AA_AA
        print(object_path)
        addr = object_path.split("/")[-1][4:].replace("_", ":")
        if addr not in self._devices:
            return
        self._devices[addr].close()
        self._devices.pop(addr)
        self.notify("devices")
        self.notify("connected-devices")
        self.emit("changed")
        self.emit("device-removed", addr)

    def connect_device(self, device: BluetoothDevice, connection: bool, callback):
        def inner_callback(client: GnomeBluetooth.Client, res: Gio.AsyncResult):
            try:
                finish = client.connect_service_finish(res)
                callback(finish)
            except:
                logger.error(f"Failed to connect to device {device.props.address}")
                callback(False)

        self._client.connect_service(
            device.get_object_path(), connection, None, inner_callback
        )

    def get_device_from_addr(self, address: str) -> BluetoothDevice:
        return self._devices[address]

    def notifier(self, name: str, args=None):
        self.notify(name)
        self.emit("changed")
        return

    @Property(value_type=object, flags="read")
    def devices(self) -> dict:
        return self._devices

    @Property(value_type=object, flags="read")
    def connected_devices(self) -> dict:
        return self._connected_devices

    @Property(value_type=str, flags="read")
    def state(self) -> str:
        return {
            GnomeBluetooth.AdapterState.ABSENT: "absent",
            GnomeBluetooth.AdapterState.ON: "on",
            GnomeBluetooth.AdapterState.TURNING_ON: "turning-on",
            GnomeBluetooth.AdapterState.TURNING_OFF: "turning-off",
            GnomeBluetooth.AdapterState.OFF: "off",
        }.get(self._client.props.default_adapter_state, "unknown")

    @Property(value_type=int, flags="read-write")
    def scanning(self) -> int:
        return self._client.props.default_adapter_setup_mode

    @scanning.setter
    def scanning(self, value):
        GLib.idle_add(
            lambda: self._client.set_property("default_adapter_setup_mode", value)
        )

    @Property(value_type=bool, default_value=False, flags="read-write")
    def enabled(self) -> str:
        return True if self.props.state in ["on", "turning-on"] else False

    @enabled.setter
    def enabled(self, value: bool):
        GLib.idle_add(
            lambda: self._client.set_property("default_adapter_powered", value)
        )
