import json
import os

import gi
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow as Window
from loguru import logger

from fabric_config.snippits.popupwindow import PopupWindow
from fabric_config.utils.icon_resolver import IconResolver
from fabric_config.utils.hyprland_monitor import HyprlandWithMonitors

gi.require_version("Glace", "0.1")
from gi.repository import Glace, GLib

CACHE_DIR = str(GLib.get_user_cache_dir()) + "/fabric"
APP_CACHE = CACHE_DIR + "/dock"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
if not os.path.exists(APP_CACHE):
    os.makedirs(APP_CACHE)


def get_docked_apps() -> list:
    docked_apps_list = []
    if os.path.exists(APP_CACHE + "/docked_apps.json"):
        with open(APP_CACHE + "/docked_apps.json", "r") as f:
            try:
                docked_apps_list = json.load(f)
            except json.JSONDecodeError:
                logger.info("[Dock] Cache file does not exist or is corrupted")
            finally:
                f.close()
    return docked_apps_list


class AppBar(Box):
    def __init__(self, parent: Window):
        self.client_buttons = {}
        self._parent = parent
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
                    on_button_press_event=lambda *_: print(
                        self._parent.get_application().actions["toggle-appmenu"][0]()
                    ),
                )
            ],
        )
        self.icon_resolver = IconResolver()
        self._manager = Glace.Manager()
        self._manager.connect("client-added", self.on_client_added)
        self._preview_image = Image()
        self._hyp = HyprlandWithMonitors()

        self.connect("notify::visible", lambda *_: print(self.is_visible()))

        self.popup_revealer = Revealer(
            child=Box(
                children=self._preview_image,
                style_classes=["window-basic", "cool-border"],
            ),
            transition_type="crossfade",
            transition_duration=400,
        )

        self.popup = PopupWindow(
            parent,
            child=self.popup_revealer,
            margin="0px 0px 120px 0px",
            visible=False,
        )

        self.popup_revealer.connect(
            "notify::child-revealed",
            lambda *_: self.popup.set_visible(False)
            if not self.popup_revealer.child_revealed
            else None,
        )

    def update_preview_image(self, client, client_button: Button):
        self.popup.set_pointing_to(client_button)

        def capture_callback(pbuf, _):
            self._preview_image.set_from_pixbuf(
                pbuf.scale_simple(pbuf.get_width() * 0.15, pbuf.get_height() * 0.15, 2)
            )
            self.popup.set_visible(True)
            self.popup_revealer.reveal()

        self._manager.capture_client(
            client=client,
            overlay_cursor=False,
            callback=capture_callback,
            user_data=None,
        )

    def on_client_added(self, _, client: Glace.Client):
        client_image = Image()
        client_button = Button(
            style_classes=["button-basic", "button-basic-props"],
            image=client_image,
            on_button_press_event=lambda _, event: client.activate()
            if event.button == 1
            else None,
            on_enter_notify_event=lambda *_: self.update_preview_image(
                client, client_button
            ),
            on_leave_notify_event=lambda *_: self.popup_revealer.unreveal(),
        )
        self.client_buttons[client.get_id()] = client_button

        client.connect(
            "notify::app-id",
            lambda *_: client_image.set_from_pixbuf(
                self.icon_resolver.get_icon_pixbuf(client.get_app_id(), 60)
            ),
        )

        client.connect(
            "notify::app-id",
            lambda *_: client_button.set_tooltip_window(
                Window(
                    child=Box(
                        style="background-color: red; min-height: 50px; min-width: 50px;"
                    ),
                    visible=False,
                    all_visible=False,
                )
            ),
        )

        client.connect(
            "notify::activated",
            lambda *_: client_button.add_style_class("active")
            if client.get_activated()
            else client_button.remove_style_class("active"),
        )

        client.connect("close", lambda *_: self.remove(client_button))
        self.add(client_button)


class DockContextMenu(Box):
    def __init__(self):
        super().__init__(
            style_classes=["cool-border", "window-basic"],
            orientation="vertical",
            all_visible=True,
            children=[
                Button(
                    label="Dock App",
                    style_classes=[
                        "button-basic",
                        "button-basic-props",
                        "button-border",
                    ],
                ),
                Box(name="prayer-info-separator"),
                Button(
                    label="Close App",
                    style_classes=[
                        "button-basic",
                        "button-basic-props",
                        "button-border",
                    ],
                ),
                Box(name="prayer-info-separator"),
                Button(
                    label="Undock App",
                    style_classes=[
                        "button-basic",
                        "button-basic-props",
                        "button-border",
                    ],
                ),
            ],
        )


class AppDock(Window):
    def __init__(self):
        super().__init__(
            layer="top",
            anchor="bottom center",
        )
        self.revealer = Revealer(
            child=Box(children=[AppBar(self)], style="padding: 20px 50px 5px 50px;"),
            transition_duration=500,
            transition_type="slide-up",
        )
        self.children = EventBox(
            events=["enter-notify", "leave-notify"],
            child=CenterBox(
                center_children=self.revealer,
                start_children=Box(
                    style="min-height: 10px; min-width: 5px;"
                ),
                end_children=Box(
                    style="min-height: 10px; min-width: 5px;"
                ),
            ),
            on_enter_notify_event=lambda *_: self.revealer.set_reveal_child(True),
            on_leave_notify_event=lambda *_: self.revealer.set_reveal_child(False),
        )
