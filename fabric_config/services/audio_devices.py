"""
Audio outputs and inputs to choose between: speakers, headphones, HDMI, ...

These are Cvc's "UI devices", the list GNOME's sound settings show. One sink
can have several ports (a laptop's speakers and headphone jack), and a card
may need a profile switch first (an unused HDMI port, a Bluetooth headset's
handsfree mode); `select()` does whatever the device needs and makes it the
default.

fabric's `Audio` keeps its mixer control private, and Cvc only announces
devices as they're added (it can't list them), so this has its own control.
"""

from dataclasses import dataclass

import gi
from fabric.core.service import Property, Service, Signal

gi.require_version("Cvc", "1.0")
from gi.repository import Cvc  # noqa: E402


@dataclass(frozen=True)
class AudioDevice:
    id: int
    is_output: bool
    description: str
    origin: str
    icon_name: str


class AudioDevices(Service):
    @Signal
    def changed(self) -> None:
        """The list of devices changed."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._devices: dict[tuple[bool, int], Cvc.MixerUIDevice] = {}
        self._active_output = -1
        self._active_input = -1

        self._control = Cvc.MixerControl(name="fabric audio devices")
        self._control.connect("output-added", lambda _, id: self._added(True, id))
        self._control.connect("input-added", lambda _, id: self._added(False, id))
        self._control.connect("output-removed", lambda _, id: self._removed(True, id))
        self._control.connect("input-removed", lambda _, id: self._removed(False, id))
        self._control.connect(
            "active-output-update", lambda _, id: self._set_active(True, id)
        )
        self._control.connect(
            "active-input-update", lambda _, id: self._set_active(False, id)
        )
        self._control.open()

    @Property(int, "readable")
    def active_output(self) -> int:
        """Id of the device the default sink plays through, or -1."""
        return self._active_output

    @Property(int, "readable")
    def active_input(self) -> int:
        """Id of the device the default source records from, or -1."""
        return self._active_input

    @property
    def outputs(self) -> list[AudioDevice]:
        return self._list(True)

    @property
    def inputs(self) -> list[AudioDevice]:
        return self._list(False)

    def select(self, device: AudioDevice):
        ui_device = self._devices.get((device.is_output, device.id))
        if ui_device is None:
            return
        if device.is_output:
            self._control.change_output(ui_device)
        else:
            self._control.change_input(ui_device)

    def _list(self, is_output: bool) -> list[AudioDevice]:
        devices = [
            AudioDevice(
                id=id,
                is_output=is_output,
                description=d.get_description() or "",
                origin=self._origin(d),
                icon_name=d.get_icon_name() or "",
            )
            for (output, id), d in self._devices.items()
            # unplugged jacks and disconnected HDMI ports stay listed by Cvc
            if output == is_output and d.props.port_available
        ]
        return sorted(devices, key=lambda d: (d.origin, d.description))

    def _origin(self, device: Cvc.MixerUIDevice) -> str:
        # an HDMI sink names its monitor ("... (HDMI) [LG QHD]"); the
        # graphics card it's on says much less
        stream = self._control.lookup_stream_id(device.get_stream_id())
        description = (stream.get_description() or "") if stream else ""
        if description.endswith("]") and "[" in description:
            return description[description.rindex("[") + 1 : -1]
        return device.get_origin() or ""

    def _lookup(self, is_output: bool, id: int) -> Cvc.MixerUIDevice | None:
        if is_output:
            return self._control.lookup_output_id(id)
        return self._control.lookup_input_id(id)

    def _added(self, is_output: bool, id: int):
        device = self._lookup(is_output, id)
        if device is None:
            return
        if (is_output, id) not in self._devices:
            # a jack being plugged in flips this without re-adding the device
            device.connect("notify::port-available", lambda *_: self.emit("changed"))
        self._devices[(is_output, id)] = device
        self.emit("changed")

    def _removed(self, is_output: bool, id: int):
        if self._devices.pop((is_output, id), None) is not None:
            self.emit("changed")

    def _set_active(self, is_output: bool, id: int):
        if is_output:
            self._active_output = id
            self.notify("active-output")
        else:
            self._active_input = id
            self.notify("active-input")
