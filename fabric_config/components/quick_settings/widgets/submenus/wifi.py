import gi
from typing import Callable

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
from loguru import logger

from fabric_config.utils.process import run_command_async

gi.require_version("AstalNetwork", "0.1")
gi.require_version("NM", "1.0")
from gi.repository import AstalNetwork as an  # noqa: E402
from gi.repository import Gio, GLib, NM  # noqa: E402

# the GI name starts with a digit, so it can't be accessed as an attribute
_AP_SECURITY = getattr(NM, "80211ApSecurityFlags")


def _freq_band(freq_mhz: int) -> str:
    if freq_mhz >= 5925:
        return "6 GHz"
    if freq_mhz >= 3000:
        return "5 GHz"
    return "2.4 GHz"


def _key_mgmt_for(ap: an.AccessPoint) -> str:
    rsn = ap.get_rsn_flags()
    # WPA3-only networks need SAE; WPA2 and mixed WPA2/WPA3 accept a PSK
    if rsn & _AP_SECURITY.KEY_MGMT_SAE and not rsn & _AP_SECURITY.KEY_MGMT_PSK:
        return "sae"
    return "wpa-psk"


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
        on_forgotten: Callable[[], None] | None = None,
        **kwargs,
    ):
        super().__init__(orientation="v", h_expand=True, spacing=0, **kwargs)
        self.ap = ap
        self.network = network
        self.on_forgotten = on_forgotten

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
                    style_classes=["submenu-card-label"],
                    ellipsize="end",
                ),
                Label(
                    label=_freq_band(ap.get_frequency()),
                    h_align="start",
                    style_classes=["submenu-card-sublabel"],
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
                    style_classes=["submenu-card-icon"],
                ),
                ssid_col,
            ],
        )
        if self.requires_password and not self.is_saved:
            left.add(
                Image(
                    icon_name="channel-secure-symbolic",
                    icon_size=11,
                    style_classes=["submenu-card-lock"],
                )
            )

        end_box = Box(spacing=4, v_align="center")
        if self.is_connected:
            end_box.add(
                Image(
                    icon_name="object-select-symbolic",
                    icon_size=14,
                    style_classes=["submenu-card-check"],
                )
            )

        row = CenterBox(
            h_expand=True,
            v_align="center",
            start_children=[left],
            end_children=[end_box] if end_box.get_children() else [],
        )

        self.main_btn = Button(style_classes=["submenu-card"], child=row, h_expand=True)
        if self.is_connected:
            self.main_btn.add_style_class("active")

        btn_row = Box(spacing=4, h_expand=True, children=[self.main_btn])
        if self.is_saved:
            self.main_btn.add_style_class("joined-left")
            forget_btn = Button(
                image=Image(icon_name="user-trash-symbolic", icon_size=12),
                style_classes=["submenu-card-forget"],
                tooltip_text="Forget network",
            )
            forget_btn.connect("clicked", self._on_forget)
            btn_row.add(forget_btn)

        self.add(btn_row)

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
        # Connect through the NetworkManager API rather than nmcli, so the
        # password never appears in a process's argv (visible to `ps`).
        nm_client: NM.Client = self.network.get_client()
        wifi = self.network.get_wifi()
        device = wifi.get_device() if wifi else None
        if not nm_client or device is None:
            self._notify_failure("NetworkManager is not available")
            return

        self.main_btn.add_style_class("connecting")

        def on_done(client: NM.Client, result: Gio.AsyncResult, add_new: bool):
            self.main_btn.remove_style_class("connecting")
            try:
                if add_new:
                    client.add_and_activate_connection_finish(result)
                else:
                    client.activate_connection_finish(result)
            except GLib.Error as e:
                self._notify_failure(e.message)

        saved = self._find_saved_connection()
        if saved is not None and not password:
            nm_client.activate_connection_async(
                saved, device, self.ap.get_path(), None, on_done, False
            )
            return

        partial = None
        if password:
            partial = NM.SimpleConnection.new()
            security = NM.SettingWirelessSecurity.new()
            security.set_property(
                NM.SETTING_WIRELESS_SECURITY_KEY_MGMT, _key_mgmt_for(self.ap)
            )
            security.set_property(NM.SETTING_WIRELESS_SECURITY_PSK, password)
            partial.add_setting(security)

        nm_client.add_and_activate_connection_async(
            partial, device, self.ap.get_path(), None, on_done, True
        )

    def _notify_failure(self, reason: str):
        run_command_async(
            [
                "notify-send",
                "-i",
                "network-wireless-error-symbolic",
                "Wi-Fi",
                f"Failed to connect to {self.ap.get_ssid()}: {reason}",
            ]
        )

    def _on_connect_with_password(self, *_):
        pw = self.password_entry.get_text().strip() if self.password_entry else None
        if self.pw_revealer:
            self.pw_revealer.set_reveal_child(False)
        self._connect(pw if pw else None)

    def _on_forget(self, _btn):
        conn = self._find_saved_connection()
        if conn is None:
            return

        def on_deleted(connection: NM.RemoteConnection, result: Gio.AsyncResult):
            try:
                connection.delete_finish(result)
            except GLib.Error as e:
                logger.error(f"[Wi-Fi] Failed to forget {self.ap.get_ssid()}: {e}")
                return
            if self.on_forgotten:
                self.on_forgotten()

        conn.delete_async(None, on_deleted)


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

        # Only one row is shown per SSID. Put the active access point first so
        # its row is the one kept; otherwise, on dual-band or mesh networks, a
        # stronger AP with the same SSID would hide the "connected" state.
        active_ap = self.wifi_device.get_active_access_point()
        active_bssid = active_ap.get_bssid() if active_ap else None
        aps = sorted(
            self.wifi_device.get_access_points(),
            key=lambda ap: (ap.get_bssid() == active_bssid, ap.get_strength()),
            reverse=True,
        )

        for ap in aps:
            ssid = ap.get_ssid()
            if ssid and ssid not in self.seen_networks:
                self.seen_networks.add(ssid)
                self.available_networks_box.add(
                    WifiNetworkRow(
                        ap,
                        self.network,
                        saved_ssids=saved_ssids,
                        on_forgotten=self.build_wifi_options,
                    )
                )


class WifiToggle(QuickSubToggle):
    def __init__(self, submenu: QuickSubMenu, client: an.Network, **kwargs):
        super().__init__(
            action_icon="network-wireless-disabled-symbolic",
            action_label="Off",
            title="Wi-Fi",
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

            def update(*_):
                # filled when connected; tinted when on but not connected
                ssid = wifi.get_ssid()
                if not wifi.get_enabled():
                    self.set_state("off")
                    self.action_label.set_label("Off")
                elif ssid:
                    self.set_state("on")
                    self.action_label.set_label(ssid)
                else:
                    self.set_state("partial")
                    self.action_label.set_label("Not connected")

            wifi.connect("notify::enabled", update)
            wifi.connect("notify::ssid", update)
            update()

            # AstalNetwork objects are plain GObjects, not fabric Services, so
            # they have bind_property() but no fabric-style bind()
            wifi.bind_property("icon-name", self.action_icon, "icon-name")

    def on_action(self, _btn):
        wifi: an.Wifi | None = self.client.get_wifi()
        if wifi:
            wifi.set_enabled(not wifi.get_enabled())
