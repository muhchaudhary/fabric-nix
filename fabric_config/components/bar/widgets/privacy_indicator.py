from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image

import fabric_config.config as config
from fabric_config.services.privacy import KINDS, UseKind

KIND_INFO: dict[UseKind, tuple[str, str]] = {
    "mic": ("Microphone", "audio-input-microphone-symbolic"),
    "camera": ("Camera", "camera-web-symbolic"),
    "screen": ("Screen sharing", "screen-shared-symbolic"),
}


class PrivacyIndicator(Button):
    """
    Shown while an app uses the microphone or camera, or shares the screen:
    an icon for each, and who in the tooltip. Click to mute the microphone.
    """

    def __init__(self, **kwargs):
        self.service = config.privacy
        self.icons: dict[UseKind, Image] = {}
        box = Box(spacing=4)
        for kind in KINDS:
            icon = self.icons[kind] = Image(
                icon_name=KIND_INFO[kind][1], icon_size=16, style_classes=[kind]
            )
            icon.set_no_show_all(True)
            box.add(icon)
        super().__init__(
            name="privacy-indicator",
            style_classes=["button-basic", "button-basic-props", "button-border"],
            child=box,
            on_clicked=lambda *_: self._toggle_mic_mute(),
            **kwargs,
        )
        self.set_no_show_all(True)
        self.service.connect("changed", lambda *_: self.sync())
        config.audio.connect("notify::microphone", lambda *_: self.sync())
        self.sync()

    def sync(self):
        lines = []
        for kind in KINDS:
            uses = self.service.in_use(kind)
            self.icons[kind].set_visible(bool(uses))
            if uses:
                apps = ", ".join(dict.fromkeys(u.app for u in uses))
                lines.append(f"{KIND_INFO[kind][0]}: {apps}")
        if self.service.in_use("mic"):
            mic = config.audio.microphone
            lines.append(
                "Click to unmute the microphone"
                if mic and mic.muted
                else "Click to mute the microphone"
            )
        self.set_tooltip_text("\n".join(lines))
        self.set_visible(bool(lines))

    def _toggle_mic_mute(self):
        mic = config.audio.microphone
        if mic is not None and self.service.in_use("mic"):
            mic.muted = not mic.muted
            self.sync()
