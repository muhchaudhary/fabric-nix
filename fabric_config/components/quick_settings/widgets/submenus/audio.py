from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label

from fabric_config.components.quick_settings.widgets.quick_settings_submenu import (
    QuickSubMenu,
)
from fabric_config.services.audio_devices import AudioDevice, AudioDevices
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


class AudioSubMenu(QuickSubMenu):
    """Pick the output (speakers, headphones, HDMI, ...) and the input."""

    def __init__(self, client: AudioDevices, **kwargs):
        self.client = client
        self.outputs = Box(orientation="v", spacing=2, h_expand=True)
        self.inputs = Box(orientation="v", spacing=2, h_expand=True)

        super().__init__(
            title="Sound",
            title_icon="audio-speakers-symbolic",
            child=Box(
                orientation="v",
                spacing=8,
                children=[self.outputs, self.inputs],
            ),
            **kwargs,
        )

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
