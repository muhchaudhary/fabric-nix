from collections.abc import Callable

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label

import fabric_config.config as config
from fabric_config.components.quick_settings.widgets.quick_settings_toggle_button import (
    QuickSettingsToggleButton,
)
from fabric_config.services.power_profiles import PROFILES


class DoNotDisturbToggle(QuickSettingsToggleButton):
    def __init__(self, **kwargs):
        super().__init__(
            action_label="Do Not Disturb",
            action_icon="notifications-disabled-symbolic",
            active=config.notifications.dnd,
            on_toggle=lambda active: setattr(config.notifications, "dnd", active),
            **kwargs,
        )
        config.notifications.connect(
            "notify::dnd", lambda *_: self.sync_active(config.notifications.dnd)
        )


class CaffeineToggle(QuickSettingsToggleButton):
    def __init__(self, **kwargs):
        super().__init__(
            action_label="Caffeine",
            action_icon="my-caffeine-on-symbolic",
            status_on="Screen stays awake",
            active=config.caffeine.active,
            on_toggle=lambda active: setattr(config.caffeine, "active", active),
            tooltip_text="Keep the screen awake",
            **kwargs,
        )
        # taking the lock can fail; show what actually happened
        config.caffeine.connect(
            "notify::active", lambda *_: self.sync_active(config.caffeine.active)
        )


class ScreenRecordToggle(QuickSettingsToggleButton):
    """Starts a region recording, or stops the running one."""

    def __init__(self, close_popup: Callable[[], object], **kwargs):
        self._close_popup = close_popup
        super().__init__(
            action_label="Record",
            action_icon="media-record-symbolic",
            status_on="Click to stop",
            status_off="Select a region",
            on_toggle=self._on_toggled,
            **kwargs,
        )
        config.sc.connect("recording", lambda _, status: self._on_recording(status))

    def _on_toggled(self, active: bool):
        # the tile lights up once wf-recorder actually starts, not on click
        self.sync_active(not active)
        if active:
            # out of the way of the region selection
            self._close_popup()
            config.sc.screencast_start()
        else:
            config.sc.screencast_stop()

    def _on_recording(self, recording: bool):
        self.sync_active(recording)
        self.set_action_label("Recording" if recording else "Record")
        self.set_action_icon(
            "media-playback-stop-symbolic" if recording else "media-record-symbolic"
        )


class ScreenshotButton(QuickSettingsToggleButton):
    def __init__(self, close_popup: Callable[[], object], **kwargs):
        self._close_popup = close_popup
        super().__init__(
            action_label="Screenshot",
            action_icon="camera-photo-symbolic",
            status_off="Select a region",
            on_toggle=self._on_clicked_shot,
            **kwargs,
        )

    def _on_clicked_shot(self, _active: bool):
        self.sync_active(False)
        self._close_popup()
        config.sc.screenshot()


PROFILE_INFO = {
    "power-saver": ("Saver", "power-profile-power-saver-symbolic"),
    "balanced": ("Balanced", "power-profile-balanced-symbolic"),
    "performance": ("Performance", "power-profile-performance-symbolic"),
}


class PowerProfileRow(Box):
    """A segmented control for power-profiles-daemon; hidden without it."""

    def __init__(self, **kwargs):
        super().__init__(
            name="power-profile-row",
            spacing=4,
            homogeneous=True,
            **kwargs,
        )
        self.buttons: dict[str, Button] = {}
        for profile in PROFILES:
            label, icon = PROFILE_INFO[profile]
            button = Button(
                name="power-profile-button",
                child=Box(
                    spacing=6,
                    h_align="center",
                    children=[Image(icon_name=icon, icon_size=16), Label(label)],
                ),
                on_clicked=lambda _, p=profile: setattr(
                    config.power_profiles, "profile", p
                ),
            )
            # hidden ones (no performance mode) stay hidden through show_all()
            button.set_no_show_all(True)
            self.buttons[profile] = button
            self.add(button)

        self.set_no_show_all(True)
        config.power_profiles.connect("notify::available", self._update)
        config.power_profiles.connect("notify::profile", self._update)
        self._update()

    def _update(self, *_):
        service = config.power_profiles
        self.set_visible(service.available)
        offered = service.profiles
        for profile, button in self.buttons.items():
            button.set_visible(profile in offered)
            if profile == service.profile:
                button.add_style_class("active")
            else:
                button.remove_style_class("active")
