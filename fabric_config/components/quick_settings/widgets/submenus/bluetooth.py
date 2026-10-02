from fabric_config.components.quick_settings.widgets.quick_settings_submenu import (
    QuickSubMenu,
    QuickSubToggle,
)
from fabric_config.widgets.toggle_pill import ToggleSwitch
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.bluetooth.service import BluetoothClient, BluetoothDevice
from gi.repository import GLib, Gio
from typing import Callable

# GnomeBluetooth does not always surface a device's battery (battery-type
# stays NONE even when the info is available), so we read BlueZ's
# org.bluez.Battery1 interface directly as a fallback.
BLUEZ_BATTERY_IFACE = "org.bluez.Battery1"


def make_battery_proxy(
    device: BluetoothDevice,
    on_changed: Callable[[], None],
    on_ready: Callable[[Gio.DBusProxy | None], None],
):
    """
    Asynchronously create a proxy onto the device's BlueZ Battery1 interface.

    `on_ready` receives the proxy (or None on failure); `on_changed` is called
    whenever its properties change. Created asynchronously so a slow BlueZ
    doesn't block the UI.
    """

    def on_proxy(_source, result: Gio.AsyncResult):
        try:
            proxy = Gio.DBusProxy.new_for_bus_finish(result)
        except GLib.Error:
            on_ready(None)
            return
        proxy.connect("g-properties-changed", lambda *_: on_changed())
        on_ready(proxy)

    Gio.DBusProxy.new_for_bus(
        Gio.BusType.SYSTEM,
        Gio.DBusProxyFlags.NONE,
        None,
        "org.bluez",
        device.device.get_object_path(),
        BLUEZ_BATTERY_IFACE,
        None,
        on_proxy,
    )


def read_battery_percentage(
    device: BluetoothDevice, proxy: Gio.DBusProxy | None
) -> int:
    """Battery %, preferring GnomeBluetooth and falling back to BlueZ."""
    percentage = round(device.battery_percentage)
    if percentage > 0:
        return percentage
    if proxy is not None:
        value = proxy.get_cached_property("Percentage")
        if value is not None:
            return int(value.unpack())
    return 0


class BluetoothDeviceBox(CenterBox):
    def __init__(self, device: BluetoothDevice, **kwargs):
        super().__init__(h_expand=True, style_classes=["submenu-card"], **kwargs)
        self.device: BluetoothDevice = device

        self.switch = ToggleSwitch(
            active=device.connected,
            on_toggled=self._on_switch_toggled,
        )

        self.battery_icon = Image(
            icon_size=14,
            style_classes=["submenu-card-battery-icon"],
        )
        self.battery_label = Label(style_classes=["submenu-card-battery-label"])
        self.battery_box = Box(
            spacing=3,
            v_align="center",
            style_classes=["submenu-card-battery"],
            children=[self.battery_icon, self.battery_label],
        )

        self._battery_proxy: Gio.DBusProxy | None = None

        self.device.connect("notify::connecting", self._on_connecting)
        self.device.connect("notify::connected", self._on_connected)
        self.device.connect("changed", self._on_battery_changed)

        self.add_start(
            Box(
                spacing=10,
                v_align="center",
                children=[
                    Image(
                        icon_name=device.icon_name + "-symbolic",
                        icon_size=16,
                        style_classes=["submenu-card-icon"],
                    ),
                    Label(
                        label=device.name,
                        style_classes=["submenu-card-label"],
                        ellipsize="end",
                    ),
                ],
            )
        )
        self.add_end(
            Box(
                spacing=8,
                v_align="center",
                children=[self.battery_box, self.switch],
            )
        )

        self._setup_battery_proxy()
        self._update_battery()

    def _on_switch_toggled(self, active: bool):
        self.device.set_property("connecting", not self.device.connected)

    def _on_connecting(self, device, _):
        self.switch.set_sensitive(not self.device.connecting)

    def _on_connected(self, *args):
        self.switch.set_sensitive(True)
        self.switch.set_active(self.device.connected)
        # BlueZ exposes/refreshes Battery1 around (dis)connection, so rebuild
        # the proxy to pick up freshly cached properties.
        self._setup_battery_proxy()
        self._update_battery()

    def _on_battery_changed(self, *args):
        self._update_battery()

    def _setup_battery_proxy(self):
        def on_ready(proxy: Gio.DBusProxy | None):
            self._battery_proxy = proxy
            self._update_battery()

        make_battery_proxy(self.device, self._update_battery, on_ready)

    def _update_battery(self):
        percentage = read_battery_percentage(self.device, self._battery_proxy)

        if not self.device.connected or percentage <= 0:
            self.battery_box.set_visible(False)
            return

        self.battery_icon.set_from_icon_name(
            f"battery-level-{min(round(percentage / 10) * 10, 100)}-symbolic", 14
        )
        self.battery_label.set_label(f"{percentage}%")
        self.battery_box.set_visible(True)


class BluetoothSubMenu(QuickSubMenu):
    def __init__(self, client: BluetoothClient, **kwargs):
        self.client = client
        self.client.connect("device-added", self.populate_new_device)
        self.client.connect("device-removed", self.remove_device)
        self._device_boxes: dict[str, BluetoothDeviceBox] = {}
        self._scan_timeout_id: int | None = None

        self.paired_devices = Box(
            orientation="v",
            spacing=2,
            h_expand=True,
            children=[
                Label(
                    label="PAIRED DEVICES",
                    style_classes=["submenu-section-header"],
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
                    style_classes=["submenu-section-header"],
                    h_align="start",
                )
            ],
        )

        for device in self.client.devices:
            self.populate_new_device(self.client, device.address)

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

    def on_scan_toggle(self, _btn: Button):
        if self._scan_timeout_id:
            self._stop_scan()
        else:
            self._start_scan()

    def _start_scan(self):
        self.client.scan()
        self.scan_button.add_style_class("scanning")
        self._scan_timeout_id = GLib.timeout_add_seconds(60, self._on_scan_timeout)

    def _stop_scan(self):
        self.client.scanning = False
        self.scan_button.remove_style_class("scanning")
        if self._scan_timeout_id:
            GLib.source_remove(self._scan_timeout_id)
            self._scan_timeout_id = None

    def _on_scan_timeout(self):
        self._scan_timeout_id = None
        self._stop_scan()
        return GLib.SOURCE_REMOVE

    def populate_new_device(self, client: BluetoothClient, address: str):
        device = client.get_device(address)
        if device is None or address in self._device_boxes:
            return
        box = BluetoothDeviceBox(device)
        self._device_boxes[address] = box
        device.connect("notify::paired", lambda *_: self._place_device_box(box))
        self._place_device_box(box)

    def _place_device_box(self, box: BluetoothDeviceBox):
        # move the box into the section matching its paired state
        section = self.paired_devices if box.device.paired else self.available_devices
        parent = box.get_parent()
        if parent is section:
            return
        if parent is not None:
            parent.remove(box)
        section.add(box)

    def remove_device(self, client: BluetoothClient, address: str):
        box = self._device_boxes.pop(address, None)
        if box is not None:
            box.destroy()


class BluetoothToggle(QuickSubToggle):
    def __init__(self, submenu: QuickSubMenu, client: BluetoothClient, **kwargs):
        super().__init__(
            action_label="Not Connected",
            action_icon="bluetooth-active-symbolic",
            submenu=submenu,
            **kwargs,
        )
        self.client = client
        self._battery_proxy: Gio.DBusProxy | None = None
        # (object path, connected) of the device the proxy was built for, so
        # the proxy is only rebuilt when that actually changes
        self._watched_device: tuple[str, bool] | None = None
        self.client.connect("notify::enabled", self.toggle_bluetooth)
        self.client.connect("device-added", self.new_device)

        self.toggle_bluetooth(client)

        for device in self.client.devices:
            self.new_device(client, device.address)

        self.connect("action-clicked", lambda *_: self.client.toggle_power())

    def _connected_label(self) -> str:
        connected = self.client.connected_devices
        if not connected:
            return "Not Connected"
        device = connected[0]
        percentage = read_battery_percentage(device, self._battery_proxy)
        return f"{device.name} · {percentage}%" if percentage > 0 else device.name

    def _watch_battery(self):
        # (Re)build a BlueZ battery proxy for the currently connected device so
        # its battery changes refresh the label; GnomeBluetooth won't notify us.
        # Devices emit "changed" often (e.g. RSSI updates), so only rebuild
        # when the watched device or its connection state changes.
        connected = self.client.connected_devices
        watched = (connected[0].device.get_object_path(), True) if connected else None
        if watched == self._watched_device:
            return
        self._watched_device = watched
        self._battery_proxy = None
        if not connected:
            return

        def on_ready(proxy: Gio.DBusProxy | None):
            # ignore a proxy that finished after the watched device changed
            if self._watched_device == watched:
                self._battery_proxy = proxy
                self._refresh_label()

        make_battery_proxy(connected[0], self._refresh_label, on_ready)

    def _refresh_label(self):
        if self.client.enabled:
            self.action_label.set_label(self._connected_label())

    def toggle_bluetooth(self, client: BluetoothClient, *_):
        if client.enabled:
            self.set_active_style(True)
            self.action_icon.set_from_icon_name("bluetooth-active-symbolic", 20)
            # Don't clobber an already-connected device's name: this fires on
            # notify::enabled, which resolves asynchronously at startup.
            self._watch_battery()
            self.action_label.set_label(self._connected_label())
        else:
            self.set_active_style(False)
            self.action_icon.set_from_icon_name("bluetooth-disabled-symbolic", 20)
            self.action_label.set_label("Disabled")

    def new_device(self, client: BluetoothClient, address):
        device = client.get_device(address)
        if device is not None:
            device.connect("changed", self.device_connected)
            # Reflect the current state right away: devices present at startup
            # populate asynchronously and may already be connected, so relying
            # on a future "changed" signal would leave the label stale.
            self.device_connected(device)

    def device_connected(self, device: BluetoothDevice):
        # the label always reflects the first connected device, so recompute it
        # on any change rather than matching the label text against device names
        self._watch_battery()
        self._refresh_label()
