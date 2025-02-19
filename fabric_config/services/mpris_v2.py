from typing import Literal, Optional, cast

import gi
from fabric.core.service import Property, Service, Signal
from fabric.utils.helpers import (
    bulk_connect,
    clamp,
    get_relative_path,
    load_dbus_xml,
    pascal_case_to_snake_case,
    snake_case_to_kebab_case,
)
from loguru import logger

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib  # noqa: E402

MPRIS_MEDIAPLAYER_BUS_NAME = "org.mpris.MediaPlayer2"
MPRIS_MEDIAPLAYER_BUS_PATH = "/org/mpris/MediaPlayer2"
# MPRIS_MEDIAPLAYER_BUS_IFACE_NODE = load_dbus_xml(
#     get_relative_path("service_assets/org.mpris.MediaPlayer2.xml")
# )

MPRIS_MEDIAPLAYER_PLAYER_BUS_NAME = "org.mpris.MediaPlayer2.Player"
MPRIS_MEDIAPLAYER_PLAYER_BUS_IFACE_NODE = load_dbus_xml(
    get_relative_path("service_assets/org.mpris.MediaPlayer2.Player.xml")
)


class MprisPlayer(Service):
    @Signal
    def closed(self, value: bool) -> bool: ...

    @Signal
    def changed(self) -> None: ...

    # TODO: why??? object
    # TypeError: can't convert return value to desired type
    @Signal
    def seeked(self, position: int) -> object: ...

    @Property(str, "readable")
    def player_name(self):
        return self.bus_name.split(".", 3)[-1].split(".")[0]

    @Property(str, "readable")
    def playback_status(self) -> Literal["Playing", "Paused", "Stopped"]:
        return GLib.Variant.get_string(
            self._proxy.get_cached_property("PlaybackStatus").get_string()  # type: ignore
        )  # type: ignore

    @Property(str, "readable")
    def loop_status(self) -> Literal["None", "Track", "Playlist"]:
        return GLib.Variant.get_string(
            self._proxy.get_cached_property("LoopStatus").get_string()  # type: ignore
        )  # type: ignore

    # TODO: Playback rate??? (Rate) idk i dont really see why someone would use this ngl

    @Property(bool, "read-write", default_value=False)
    def shuffle(self) -> bool:
        return self._proxy.get_cached_property("Shuffle").get_boolean()  # type: ignore

    @shuffle.setter
    def shuffle(self, is_shuffle: bool) -> None:
        self._proxy_update_property(
            "Shuffle", GLib.Variant("b", value=is_shuffle)
        ) if self.can_control else None

    @Property(object, "readable")
    def metadata(self) -> dict:
        return self._proxy.get_cached_property("Metadata")  # type: ignore

        # TODO should there be specfic props for stuff inside metadata? I dont think so tbh

    @Property(float, "read-write")
    def volume(self) -> float:
        return self._proxy.get_cached_property("Volume").get_double()  # type: ignore

    @volume.setter
    def volume(self, volume: float) -> None:
        self._proxy_update_property(
            "Volume",
            GLib.Variant("d", clamp(value=volume, min_value=0.0, max_value=1.0)),
        ) if self.can_control else None

    @Property(int, "read-write", default_value=0)
    def position(self) -> int:
        return self._proxy.get_cached_property("Position").get_int64()  # type: ignore

    @position.setter
    def position(self, new_pos: int) -> None:
        self._proxy_call(
            "SetPosition",
            GLib.Variant(
                "(ox)",
                (self.metadata["mpris:trackid"], new_pos),
            ),
        )

    # TODO: consider MinimumRate, MaximumRate

    @Property(bool, "readable", default_value=False)
    def can_go_next(self) -> bool:
        return self._proxy.get_cached_property("CanGoNext").get_boolean()

    @Property(bool, "readable", default_value=False)
    def can_go_previous(self) -> bool:
        return self._proxy.get_cached_property("CanGoPrevious").get_boolean()

    @Property(bool, "readable", default_value=False)
    def can_play(self) -> bool:
        return self._proxy.get_cached_property("CanPlay").get_boolean()

    @Property(bool, "readable", default_value=False)
    def can_pause(self) -> bool:
        return self._proxy.get_cached_property("CanPause").get_boolean()

    @Property(bool, "readable", default_value=False)
    def can_seek(self) -> bool:
        return self._proxy.get_cached_property("CanSeek").get_boolean()

    @Property(bool, "readable", default_value=False)
    def can_control(self) -> bool:
        return self._proxy.get_cached_property("CanControl").get_boolean()

    def __init__(self, bus_name: str, **kwargs):
        super().__init__(**kwargs)
        self.bus_name: str = bus_name
        self._proxy: Gio.DBusProxy | None = None

        # Ahoy!
        self.do_register()

    def do_register(self) -> None:  # the bus id
        interface = MPRIS_MEDIAPLAYER_PLAYER_BUS_IFACE_NODE.interfaces[0]
        cast(Gio.DBusInterface, interface)
        self._proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE,
            interface,
            self.bus_name,
            MPRIS_MEDIAPLAYER_BUS_PATH,
            MPRIS_MEDIAPLAYER_PLAYER_BUS_NAME,
        )

        bulk_connect(
            self._proxy,
            {
                "g-properties-changed": self._do_handle_properties_changed,
                "g-signal": self._do_handle_signal_changed,
                "notify::g-name-owner": self._on_name_owner_change,
            },
        )

    def _proxy_update_property(self, property_name: str, value: GLib.Variant):
        self._proxy.call_sync(
            "org.freedesktop.DBus.Properties.Set",
            GLib.Variant(
                "(ssv)",
                (
                    MPRIS_MEDIAPLAYER_PLAYER_BUS_NAME,
                    property_name,
                    value,
                ),
            ),
            Gio.DBusCallFlags.NONE,
            1000,
        ) if self._proxy else None

    def _do_handle_properties_changed(
        self, proxy: Gio.DBusProxy, changed_properties, invalidated_properties: str
    ):
        for prop_name in set(
            [
                snake_case_to_kebab_case(pascal_case_to_snake_case(x))
                for x in changed_properties.keys()
            ]
        ).intersection([prop.name for prop in self.get_properties()]):
            self.notify(prop_name)

        self.changed()

    def _do_handle_signal_changed(
        self,
        proxy: Gio.DBusProxy,
        sender_name: str,
        signal_name: str,
        params: tuple[GLib.Variant],
    ):
        # Only One Signal for Mpris
        if signal_name == "Seeked":
            self.seeked(params[0])

    def _proxy_call(self, method_name: str, parameter: Optional[GLib.Variant]):
        self._proxy.call(
            method_name,
            None,
            Gio.DBusCallFlags.NONE,
            self._proxy.get_default_timeout(),
            None,
            self._do_method_callback,
            pascal_case_to_snake_case(method_name),
        )

    def _do_method_callback(self, _, res: Gio.AsyncResult, user_data):
        try:
            self._proxy.call_finish(res)
        except Exception:
            logger.error(
                f"[MPRIS-{self.bus_name}] Failed to invoke method: {user_data}"
            )

    def _on_name_owner_change(self, proxy: Gio.DBusProxy, _):
        if not self._proxy.get_name_owner():
            # proxy is automatically destroyed
            self.closed(True)

    # Methods
    def next(self):
        self._proxy_call("Next", None) if self.can_go_next else None

    def previous(self):
        self._proxy_call("Previous", None) if self.can_go_previous else None

    def pause(self):
        self._proxy_call("Pause", None) if self.can_pause else None

    def play_pause(self):
        self._proxy_call("PlayPause", None) if self.can_pause else logger.error(
            f"[MPRIS-{self.bus_name}] `play_pause` is not supported by this player"
        )

    def stop(self):
        self._proxy_call("Stop", None) if self.can_control else logger.error(
            f"[MPRIS-{self.bus_name}] `stop` is not supported by this player"
        )

    def play(self):
        self._proxy_call("Play", None) if self.can_play else None

    def seek(self, time_in_us: int):
        self._proxy_call(
            "Seek", GLib.Variant.new_int64(time_in_us)
        ) if self.can_seek else None

    # No need for SetPositition, that is handled by the setter

    # Ignoring OpenUri


class MprisPlayerManager(Service):
    @Signal
    def player_appeared(self, player: MprisPlayer) -> MprisPlayer:
        logger.info(f"[MPRIS] Found Player: {player.bus_name}")
        self._players[player.bus_name] = player
        self.notify("players")
        return player

    @Signal
    def player_vanished(self, bus_name: str) -> str:
        logger.info(f"[MPRIS] Lost Player: {bus_name}")
        self._players.pop(bus_name)
        self.notify("players")
        return bus_name

    @Property(dict[str, MprisPlayer], "readable")
    def players(self):
        return self._players

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._players: dict[str, MprisPlayer] = {}

        # ahoy
        self.do_register()

    def do_register(self):
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        bus.signal_subscribe(
            "org.freedesktop.DBus",
            "org.freedesktop.DBus",
            "NameOwnerChanged",
            "/org/freedesktop/DBus",
            None,
            Gio.DBusSignalFlags.NONE,
            self.on_name_owner_change,
        )

        # This is a hack so that we can see the new players on startup and get the signal to fire
        GLib.idle_add(
            lambda: [
                self.do_handle_new_player(player)
                for player in filter(
                    lambda x: x.startswith(MPRIS_MEDIAPLAYER_BUS_NAME),
                    bus.call_sync(
                        "org.freedesktop.DBus",
                        "/org/freedesktop/DBus",
                        "org.freedesktop.DBus",
                        "ListNames",
                        GLib.Variant("()", ()),
                        GLib.VariantType("(as)"),  # type: ignore
                        Gio.DBusCallFlags.NONE,
                        -1,
                        None,
                    ).get_child_value(0),
                )
            ]
        )

    def on_name_owner_change(
        self,
        conn,
        sender_name: str,
        object_path: str,
        interface_name: str,
        signal_name: str,
        user_data,
        *params,
    ) -> None:
        name, old_owner, new_owner = user_data
        if not name.startswith(MPRIS_MEDIAPLAYER_BUS_NAME):
            return

        if old_owner == "" and new_owner != "":
            self.do_handle_new_player(name)

    def do_handle_new_player(self, bus_name: str):
        if bus_name in self._players.keys():
            return

        player = MprisPlayer(bus_name)
        player.connect(
            "closed",
            lambda *_: self.player_vanished(bus_name),
        )
        self.player_appeared(player)
