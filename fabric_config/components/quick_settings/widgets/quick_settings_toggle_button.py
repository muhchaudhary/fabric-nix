from collections.abc import Callable

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label


class QuickSettingsToggleButton(Box):
    def __init__(
        self,
        action_label: str = "Toggle",
        action_icon: str = "package-x-generic-symbolic",
        active: bool = False,
        on_toggle: Callable[[bool], object] | None = None,
        pixel_size: int = 20,
        **kwargs,
    ):
        self._active = active
        self._on_toggle = on_toggle
        self.pixel_size = pixel_size

        self.action_icon = Image(
            name="panel-icon",
            icon_name=action_icon,
            icon_size=pixel_size,
        )
        self.action_label = Label(
            name="panel-text", label=action_label, ellipsization="end"
        )
        self.action_button = Button(
            name="quicksettings-toggle-standalone",
            child=Box(
                h_expand=True,
                v_align="center",
                children=[self.action_icon, self.action_label],
            ),
        )
        self.action_button.connect("clicked", self._on_clicked)

        super().__init__(
            name="quicksettings-togglebutton",
            v_align="start",
            **kwargs,
        )
        self.pack_start(self.action_button, True, True, 0)

        if active:
            self.add_style_class("active")

    def _on_clicked(self, _):
        self.toggle()

    def toggle(self):
        self.set_active(not self._active)

    def set_active(self, active: bool):
        self.sync_active(active)
        if self._on_toggle:
            self._on_toggle(active)

    def sync_active(self, active: bool):
        """Show `active` without calling back (to follow outside changes)."""
        self._active = active
        if active:
            self.add_style_class("active")
        else:
            self.remove_style_class("active")

    @property
    def active(self) -> bool:
        return self._active

    def set_action_label(self, label: str):
        self.action_label.set_label(label)

    def set_action_icon(self, icon_name: str):
        self.action_icon.set_from_icon_name(icon_name, 1)
        self.action_icon.set_pixel_size(self.pixel_size)
