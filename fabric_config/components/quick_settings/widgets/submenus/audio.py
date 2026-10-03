from fabric.audio.service import Audio, AudioStream
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scale import Scale
from fabric.widgets.scrolledwindow import ScrolledWindow

from fabric_config.components.quick_settings.widgets.quick_settings_submenu import (
    QuickSubMenu,
)
from fabric_config.services.audio_devices import AudioDevice, AudioDevices
from fabric_config.utils.icon_resolver import get_icon_resolver
from gi.repository import Gtk


def device_icon(device: AudioDevice) -> str:
    """
    A symbolic icon the theme has for the device. Cvc's names get specific
    ("audio-headset-bluetooth", "audio-card-analog-pci"), so drop trailing
    parts until one exists.
    """
    theme = Gtk.IconTheme.get_default()
    parts = device.icon_name.split("-") if device.icon_name else []
    while parts:
        name = "-".join(parts) + "-symbolic"
        if theme.has_icon(name):
            return name
        parts.pop()
    return (
        "audio-speakers-symbolic"
        if device.is_output
        else "audio-input-microphone-symbolic"
    )


class AudioDeviceRow(Button):
    def __init__(self, device: AudioDevice, active: bool, **kwargs):
        labels = Box(
            orientation="v",
            spacing=1,
            v_align="center",
            children=[
                Label(
                    label=device.description,
                    h_align="start",
                    style_classes=["submenu-card-label"],
                    ellipsization="end",
                )
            ],
        )
        if device.origin:
            labels.add(
                Label(
                    label=device.origin,
                    h_align="start",
                    style_classes=["submenu-card-sublabel"],
                    ellipsization="end",
                )
            )

        super().__init__(
            style_classes=["submenu-card"],
            h_expand=True,
            child=CenterBox(
                h_expand=True,
                v_align="center",
                start_children=[
                    Box(
                        spacing=10,
                        v_align="center",
                        children=[
                            Image(
                                icon_name=device_icon(device),
                                icon_size=16,
                                style_classes=["submenu-card-icon"],
                            ),
                            labels,
                        ],
                    )
                ],
                end_children=[
                    Image(
                        icon_name="object-select-symbolic",
                        icon_size=14,
                        style_classes=["submenu-card-check"],
                    )
                ]
                if active
                else [],
            ),
            **kwargs,
        )
        if active:
            self.add_style_class("active")


class AppVolumeRow(Box):
    """One app's volume: icon (click to mute), name, what it plays, slider."""

    ICON_SIZE = 20

    def __init__(self, stream: AudioStream, **kwargs):
        self.stream = stream
        # streams name the app ("spotify", "Zen"), and their own icons are
        # generic ("audio"), so look the app up like the dock does
        app = stream.name or stream.description or "Unknown"
        self.icon = Image(
            pixbuf=get_icon_resolver().get_icon_pixbuf(app.lower(), self.ICON_SIZE)
        )
        self.mute_button = Button(
            child=self.icon,
            tooltip_text="Mute",
            style_classes=["app-volume-mute"],
        )
        self.mute_button.connect(
            "clicked", lambda *_: setattr(stream, "muted", not stream.muted)
        )
        self.name_label = Label(
            label=app[:1].upper() + app[1:],
            h_align="start",
            style_classes=["submenu-card-label"],
            ellipsization="end",
        )
        self.media_label = Label(
            h_align="start",
            style_classes=["submenu-card-sublabel"],
            ellipsization="end",
        )
        self.value_label = Label(style_classes=["submenu-card-sublabel"])
        self.scale = Scale(
            min_value=0,
            max_value=100,
            increments=(5, 10),
            name="quicksettings-slider",
            h_expand=True,
        )
        self.scale.connect(
            "change-value", lambda _, __, value: setattr(stream, "volume", value)
        )

        super().__init__(
            orientation="v",
            style_classes=["submenu-card", "app-volume"],
            children=[
                Box(
                    spacing=10,
                    children=[
                        self.mute_button,
                        Box(
                            orientation="v",
                            spacing=1,
                            v_align="center",
                            h_expand=True,
                            children=[self.name_label, self.media_label],
                        ),
                        self.value_label,
                    ],
                ),
                self.scale,
            ],
            **kwargs,
        )

        self._handler = stream.connect("changed", self.sync)
        self.connect("destroy", lambda *_: stream.disconnect(self._handler))
        self.sync()

    def sync(self, *_):
        stream = self.stream
        volume = round(stream.volume)
        self.scale.set_value(volume)
        self.scale.set_sensitive(not stream.muted)
        self.value_label.set_label("Muted" if stream.muted else f"{volume}%")
        self.mute_button.set_tooltip_text("Unmute" if stream.muted else "Mute")
        if stream.muted:
            self.add_style_class("muted")
        else:
            self.remove_style_class("muted")

        # the description is often what's playing (a tab's title); skip it
        # when it only repeats the app's name
        media = stream.description or ""
        self.media_label.set_label(media)
        self.media_label.set_visible(
            bool(media) and media.lower() != (stream.name or "").lower()
        )


class AudioSubMenu(QuickSubMenu):
    """
    Pick the output (speakers, headphones, HDMI, ...) and the input, and set
    each app's volume.
    """

    def __init__(self, client: AudioDevices, audio: Audio, **kwargs):
        self.client = client
        self.audio = audio
        self.outputs = Box(orientation="v", spacing=2, h_expand=True)
        self.inputs = Box(orientation="v", spacing=2, h_expand=True)
        self.apps = Box(orientation="v", spacing=2, h_expand=True)
        self.app_list = Box(orientation="v", spacing=2, h_expand=True)
        self.apps.add(
            Label(
                label="APPLICATIONS",
                style_classes=["submenu-section-header"],
                h_align="start",
            )
        )
        self.apps.add(self.app_list)
        self._app_rows: dict[int, AppVolumeRow] = {}

        super().__init__(
            title="Sound",
            title_icon="audio-speakers-symbolic",
            # grows with its content, then scrolls
            child=ScrolledWindow(
                max_content_size=(-1, 480),
                propagate_width=True,
                propagate_height=True,
                h_scrollbar_policy="never",
                child=Box(
                    orientation="v",
                    spacing=8,
                    children=[self.apps, self.outputs, self.inputs],
                ),
            ),
            **kwargs,
        )

        audio.connect("notify::applications", self.sync_apps)
        self.sync_apps()

        client.connect("changed", self.rebuild)
        client.connect("notify::active-output", self.rebuild)
        client.connect("notify::active-input", self.rebuild)
        self.rebuild()

    def rebuild(self, *_):
        for box, header, devices, active in (
            (self.outputs, "OUTPUT", self.client.outputs, self.client.active_output),
            (self.inputs, "INPUT", self.client.inputs, self.client.active_input),
        ):
            for child in box.get_children():
                child.destroy()
            box.set_visible(bool(devices))
            if not devices:
                continue
            box.add(
                Label(
                    label=header,
                    style_classes=["submenu-section-header"],
                    h_align="start",
                )
            )
            for device in devices:
                row = AudioDeviceRow(device, device.id == active)
                row.connect("clicked", lambda _, d=device: self.client.select(d))
                box.add(row)

    def sync_apps(self, *_):
        streams = {
            stream.id: stream
            for stream in self.audio.applications
            # notification and other event sounds come and go too quickly
            if not stream.stream.is_event_stream()
        }
        for id in list(self._app_rows):
            if id not in streams:
                self._app_rows.pop(id).destroy()
        for id, stream in streams.items():
            if id not in self._app_rows:
                row = AppVolumeRow(stream)
                self._app_rows[id] = row
                self.app_list.add(row)
        self.apps.set_visible(bool(self._app_rows))
