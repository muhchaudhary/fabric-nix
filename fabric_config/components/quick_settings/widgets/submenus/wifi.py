import gi
import shlex

from fabric_config.components.quick_settings.widgets.quick_settings_submenu import (
    QuickSubMenu,
    QuickSubToggle,
)
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.widgets.revealer import Revealer
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.utils import exec_shell_command_async

gi.require_version("AstalNetwork", "0.1")
gi.require_version("NM", "1.0")
from gi.repository import AstalNetwork as an  # noqa: E402
from gi.repository import GLib, NM  # noqa: E402


def _freq_band(freq_mhz: int) -> str:
    if freq_mhz >= 5925:
        return "6 GHz"
    if freq_mhz >= 3000:
        return "5 GHz"
    return "2.4 GHz"


def _get_saved_ssids(network: an.Network) -> set[str]:
    nm_client: NM.Client = network.get_client()
    if not nm_client:
        return set()
    saved: set[str] = set()
    for conn in nm_client.get_connections():
        ws = conn.get_setting_wireless()
        if ws:
            raw = ws.get_ssid()
            if raw:
                saved.add(NM.utils_ssid_to_utf8(raw.get_data()))
    return saved


class WifiNetworkRow(Box):
    def __init__(
        self,
        ap: an.AccessPoint,
        network: an.Network,
        saved_ssids: set[str],
        **kwargs,
    ):
        super().__init__(orientation="v", h_expand=True, spacing=0, **kwargs)
        self.ap = ap
        self.network = network

        wifi = network.get_wifi()
        active_ap = wifi.get_active_access_point() if wifi else None
        self.is_connected = (
            active_ap is not None and active_ap.get_bssid() == ap.get_bssid()
        )
        self.requires_password = ap.get_requires_password()
        self.is_saved = ap.get_ssid() in saved_ssids

        ssid_col = Box(
            orientation="v",
            spacing=1,
            v_align="center",
            children=[
                Label(
                    label=ap.get_ssid(),
                    h_align="start",
                    name="submenu-card-label",
                    ellipsize="end",
                ),
                Label(
                    label=_freq_band(ap.get_frequency()),
                    h_align="start",
                    name="submenu-card-sublabel",
                ),
            ],
        )

        left = Box(
            spacing=10,
            v_align="center",
            children=[
                Image(
                    icon_name=ap.get_icon_name(),
                    icon_size=16,
                    name="submenu-card-icon",
                ),
                ssid_col,
            ],
        )
        if self.requires_password and not self.is_saved:
            left.add(
                Image(
                    icon_name="channel-secure-symbolic",
                    icon_size=11,
                    name="submenu-card-lock",
                )
            )

        end_box = Box(spacing=4, v_align="center")
        if self.is_connected:
            end_box.add(
                Image(
                    icon_name="object-select-symbolic",
                    icon_size=14,
                    name="submenu-card-check",
                )
            )
        if self.is_saved:
            forget_btn = Button(
                image=Image(icon_name="user-trash-symbolic", icon_size=12),
                name="submenu-card-forget",
                tooltip_text="Forget network",
            )
            forget_btn.connect("clicked", self._on_forget)
            end_box.add(forget_btn)

        row = CenterBox(
            h_expand=True,
            v_align="center",
            start_children=[left],
            end_children=[end_box] if end_box.get_children() else [],
        )

        self.main_btn = Button(name="submenu-card", child=row, h_expand=True)
        if self.is_connected:
            self.main_btn.add_style_class("active")
        self.add(self.main_btn)

        if self.requires_password and not self.is_saved:
            self.password_entry = Entry(
                name="submenu-password-entry",
                h_expand=True,
                visibility=False,
            )
            self.password_entry.set_placeholder_text("Password")
            connect_btn = Button(label="Connect", name="submenu-title-action")

            pw_box = Box(
                spacing=6,
                h_expand=True,
                name="submenu-password-row",
                children=[self.password_entry, connect_btn],
            )
            self.pw_revealer = Revealer(
                child=pw_box,
                transition_type="slide-down",
                h_expand=True,
                transition_duration=150,
            )
            self.add(self.pw_revealer)

            connect_btn.connect("clicked", self._on_connect_with_password)
            self.password_entry.connect("activate", self._on_connect_with_password)
        else:
            self.pw_revealer = None
            self.password_entry = None

        self.main_btn.connect("clicked", self._on_click)

    def _find_saved_connection(self) -> NM.RemoteConnection | None:
        nm_client: NM.Client = self.network.get_client()
        if not nm_client:
            return None
        ssid = self.ap.get_ssid()
        for conn in nm_client.get_connections():
            ws = conn.get_setting_wireless()
            if ws:
                raw = ws.get_ssid()
                if raw and NM.utils_ssid_to_utf8(raw.get_data()) == ssid:
                    return conn  # type: ignore
        return None

    def _on_click(self, _btn):
        if self.is_connected:
            return
        if self.pw_revealer:
            self.pw_revealer.set_reveal_child(not self.pw_revealer.get_reveal_child())
        else:
            self._connect()

    def _connect(self, password: str | None = None):
        bssid = shlex.quote(self.ap.get_bssid())
        cmd = f"nmcli device wifi connect {bssid}"
        if password:
            cmd += f" password {shlex.quote(password)}"
        self.main_btn.add_style_class("connecting")

        ssid = self.ap.get_ssid()

        def on_done(output: str):
            self.main_btn.remove_style_class("connecting")
            if "Error" in output or "error" in output:
                exec_shell_command_async(
                    f"notify-send 'Wi-Fi' {shlex.quote(f'Failed to connect to {ssid}')} -i network-wireless-error-symbolic",
                    lambda *_: None,
                )

        exec_shell_command_async(cmd, on_done)

    def _on_connect_with_password(self, *_):
        pw = self.password_entry.get_text().strip() if self.password_entry else None
        if self.pw_revealer:
            self.pw_revealer.set_reveal_child(False)
        self._connect(pw if pw else None)

    def _on_forget(self, _btn):
        conn = self._find_saved_connection()
        if conn:
            uuid = conn.get_uuid()
            exec_shell_command_async(
                f"nmcli connection delete {shlex.quote(uuid)}", lambda *_: None
            )


class WifiSubMenu(QuickSubMenu):
    def __init__(self, network: an.Network, **kwargs):
        self.network = network
        self.wifi_device = self.network.get_wifi()
        self._scan_timeout_id: int | None = None
        self._build_timeout_id: int | None = None
        self._needs_rebuild = True

        if isinstance(self.wifi_device, an.Wifi):
            self.wifi_device.connect("notify::scanning", self._on_scanning_changed)
            self.wifi_device.connect(
                "notify::access-points", lambda *_: self._schedule_build()
            )

        self.available_networks_box = Box(
            orientation="v", spacing=2, h_expand=True, name="submenu-list"
        )
        self.seen_networks: set[str] = set()

        self.scan_button = Button(
            image=Image(icon_name="view-refresh-symbolic", icon_size=14),
            name="submenu-title-action",
            tooltip_text="Scan for networks",
        )
        self.scan_button.connect("clicked", self._on_scan_click)

        self.child = ScrolledWindow(
            min_content_size=(-1, 260),
            max_content_size=(-1, 260),
            propagate_width=True,
            child=self.available_networks_box,
        )

        super().__init__(
            title="Wi-Fi",
            title_icon="network-wireless-symbolic",
            title_action=self.scan_button,
            child=self.child,
            **kwargs,
        )

        # Rebuild when submenu opens, if dirty
        self.revealer.connect("notify::reveal-child", self._on_reveal_changed)

    def _schedule_build(self):
        if self._build_timeout_id:
            GLib.source_remove(self._build_timeout_id)
            self._build_timeout_id = None
        if self.revealer.get_reveal_child():
            # Visible: debounce rapid signals, rebuild after 2s of quiet
            self._build_timeout_id = GLib.timeout_add(2000, self._do_scheduled_build)
        else:
            # Hidden: just mark dirty, rebuild on next open
            self._needs_rebuild = True

    def _do_scheduled_build(self):
        self._build_timeout_id = None
        self.build_wifi_options()
        return GLib.SOURCE_REMOVE

    def _on_reveal_changed(self, revealer, _param):
        if revealer.get_reveal_child() and self._needs_rebuild:
            self.build_wifi_options()

    def _on_scan_click(self, _btn):
        if self.wifi_device and not self.wifi_device.get_scanning():
            self.wifi_device.scan()

    def _on_scanning_changed(self, wifi, _param):
        if wifi.get_scanning():
            self.scan_button.add_style_class("scanning")
            if self._scan_timeout_id:
                GLib.source_remove(self._scan_timeout_id)
            self._scan_timeout_id = GLib.timeout_add_seconds(60, self._on_scan_timeout)
        else:
            self.scan_button.remove_style_class("scanning")
            if self._scan_timeout_id:
                GLib.source_remove(self._scan_timeout_id)
                self._scan_timeout_id = None
        self.build_wifi_options()

    def _on_scan_timeout(self):
        self.scan_button.remove_style_class("scanning")
        self._scan_timeout_id = None
        return GLib.SOURCE_REMOVE

    def build_wifi_options(self):
        if not isinstance(self.wifi_device, an.Wifi):
            return
        self._needs_rebuild = False

        saved_ssids = _get_saved_ssids(self.network)

        self.available_networks_box.children = []
        self.seen_networks.clear()

        aps = sorted(
            self.wifi_device.get_access_points(),
            key=lambda ap: ap.get_strength(),
            reverse=True,
        )

        for ap in aps:
            ssid = ap.get_ssid()
            if ssid and ssid not in self.seen_networks:
                self.seen_networks.add(ssid)
                self.available_networks_box.add(
                    WifiNetworkRow(ap, self.network, saved_ssids=saved_ssids)
                )


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
            self.action_label.set_label(
                wifi.get_ssid() if wifi.get_ssid() else "Not Connected"
            )
            self.set_active_style(wifi.get_enabled())

            wifi.connect(
                "notify::enabled",
                lambda *_: [
                    self.set_active_style(wifi.get_enabled()),
                    self.action_label.set_label("Wifi Disabled")
                    if not wifi.get_enabled()
                    else self.action_label.set_label(wifi.get_ssid()),
                ],
            )

            wifi.bind("icon-name", "icon-name", self.action_icon)
            wifi.bind("ssid", "label", self.action_label)

    def on_action(self, _btn):
        wifi: an.Wifi | None = self.client.get_wifi()
        if wifi:
            wifi.set_enabled(not wifi.get_enabled())
