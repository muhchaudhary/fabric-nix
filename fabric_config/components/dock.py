import json

import gi
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow as Window
from hyprland_toplevel_streamer import HyprlandFrameCapture
from loguru import logger

from fabric_config.snippits.popupwindow import PopupWindow
from fabric_config.utils.icon_resolver import get_icon_resolver
from fabric_config.utils.hyprland_monitor import get_hyprland_monitors

gi.require_version("Glace", "0.1")
from gi.repository import GdkPixbuf, Glace, GLib  # noqa: E402


class AppBar(Box):
    def __init__(self, parent: Window):
        self.client_buttons = {}
        self._parent = parent
        self._hide_timeout_id = None
        self._preview_timeout_id = None
        super().__init__(
            spacing=10,
            name="app-bar",
            style_classes=["window-basic", "cool-border"],
            children=[
                Button(
                    image=Image(
                        icon_name="view-app-grid-symbolic",
                        icon_size=60,
                    ),
                    on_button_press_event=lambda *_: (
                        self._parent.get_application().actions["toggle-appmenu"][0]()
                    ),
                )
            ],
        )
        self.icon_resolver = get_icon_resolver()
        self._manager = Glace.Manager()
        self._manager.connect("client-added", self.on_client_added)
        self._capture = HyprlandFrameCapture()
        self._preview_image = Image()

        self.connect(
            "notify::visible",
            lambda *_: logger.debug(f"[Dock] visible={self.is_visible()}"),
        )

        self.popup_revealer = Revealer(
            child=Box(
                children=self._preview_image,
                style_classes=["window-basic", "cool-border"],
            ),
            transition_type="slide-up",
            transition_duration=150,
        )

        self.popup = PopupWindow(
            parent,
            child=Box(style="min-height: 1px", children=self.popup_revealer),
            margin="0px 0px 120px 0px",
            visible=False,
        )

        self.popup_revealer.connect(
            "notify::child-revealed",
            lambda *_: (
                self.popup.set_visible(False)
                if not self.popup_revealer.child_revealed
                else None
            ),
        )

    def _schedule_hide(self):
        self._cancel_hide()
        self._hide_timeout_id = GLib.timeout_add(200, self._do_hide)

    def _cancel_hide(self):
        if self._hide_timeout_id is not None:
            GLib.source_remove(self._hide_timeout_id)
            self._hide_timeout_id = None

    def _do_hide(self):
        self._hide_timeout_id = None
        self.popup_revealer.unreveal()
        return False

    def force_hide(self):
        self._cancel_hide()
        self._cancel_preview()
        self.popup_revealer.unreveal()
        self.popup.set_visible(False)

    def _resolve_address(self, client: Glace.Client) -> int | None:
        """Map a Glace client to its Hyprland window address.

        Glace clients don't expose the address the capture package needs, so
        match against Hyprland's client list by title (and class as a tiebreaker).
        """
        title = client.get_title()
        app_id = client.get_app_id()
        try:
            # query the IPC socket directly instead of spawning `hyprctl`
            clients = json.loads(
                get_hyprland_monitors().send_command("j/clients").reply
            )
        except Exception as e:
            logger.error(f"[Dock] fetching Hyprland clients failed: {e}")
            return None

        candidates = [
            c for c in clients if c.get("title") == title and c.get("class") == app_id
        ] or [c for c in clients if c.get("title") == title]
        if not candidates:
            return None
        return int(candidates[0]["address"], 16)

    def _schedule_preview(self, client, client_button: Button):
        # Capturing a frame is synchronous, so only do it once the pointer has
        # rested on a button, not for every button it passes over.
        self._cancel_hide()
        self._cancel_preview()
        self._preview_timeout_id = GLib.timeout_add(
            150, self._do_preview, client, client_button
        )

    def _cancel_preview(self):
        if self._preview_timeout_id is not None:
            GLib.source_remove(self._preview_timeout_id)
            self._preview_timeout_id = None

    def _do_preview(self, client, client_button: Button):
        self._preview_timeout_id = None
        self.update_preview_image(client, client_button)
        return False

    def update_preview_image(self, client, client_button: Button):
        self._cancel_hide()
        self.popup.animate_pointing_to(client_button)

        address = self._resolve_address(client)
        if address is None:
            logger.error(f"[Dock] could not resolve address for '{client.get_title()}'")
            return

        try:
            frame = self._capture.capture(address, overlay_cursor=False, rgba=True)
        except Exception as e:
            logger.error(f"[Dock] capture failed for '{client.get_title()}': {e}")
            return

        pbuf = GdkPixbuf.Pixbuf.new_from_bytes(
            GLib.Bytes.new(frame.data),
            GdkPixbuf.Colorspace.RGB,
            True,  # has_alpha
            8,  # bits per sample
            frame.width,
            frame.height,
            frame.rowstride,
        )
        self._preview_image.set_from_pixbuf(
            pbuf.scale_simple(
                int(pbuf.get_width() * 0.2),
                int(pbuf.get_height() * 0.2),
                GdkPixbuf.InterpType.BILINEAR,
            )
        )
        self.popup.set_visible(True)
        self.popup_revealer.reveal()

    def on_client_added(self, _, client: Glace.Client):
        client_image = Image()
        client_button = Button(
            style_classes=["button-basic", "button-basic-props"],
            image=client_image,
            on_button_press_event=lambda _, event: (
                client.activate() if event.button == 1 else None
            ),
            on_enter_notify_event=lambda *_: self._schedule_preview(
                client, client_button
            ),
            on_leave_notify_event=lambda *_: (
                self._cancel_preview(),
                self._schedule_hide(),
            ),
        )
        self.client_buttons[client.get_id()] = client_button

        client.connect(
            "notify::app-id",
            lambda *_: client_image.set_from_pixbuf(
                self.icon_resolver.get_icon_pixbuf(client.get_app_id(), 60)
            ),
        )

        client.connect(
            "notify::activated",
            lambda *_: (
                client_button.add_style_class("active")
                if client.get_activated()
                else client_button.remove_style_class("active")
            ),
        )

        def on_close(*_):
            self.client_buttons.pop(client.get_id(), None)
            client_button.destroy()

        client.connect("close", on_close)
        self.add(client_button)


class AppDock(Window):
    def __init__(self):
        super().__init__(
            layer="top",
            anchor="bottom center",
        )
        app_bar = AppBar(self)
        self.revealer = Revealer(
            child=Box(children=[app_bar], style="padding: 20px 50px 5px 50px;"),
            transition_duration=500,
            transition_type="slide-up",
        )
        self.children = EventBox(
            events=["enter-notify", "leave-notify"],
            child=CenterBox(
                center_children=self.revealer,
                start_children=Box(style="min-height: 10px; min-width: 5px;"),
                end_children=Box(style="min-height: 10px; min-width: 5px;"),
            ),
            on_enter_notify_event=lambda *_: self.revealer.set_reveal_child(True),
            on_leave_notify_event=lambda *_: (
                self.revealer.set_reveal_child(False),
                app_bar.force_hide(),
            ),
        )
