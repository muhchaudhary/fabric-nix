from collections.abc import Callable
from fabric.widgets.button import Button
from fabric.widgets.box import Box
from fabric.widgets.label import Label


class TogglePill(Button):
    """A pill-shaped toggle button with on/off labels and a smooth CSS transition.

    CSS target: name="toggle-pill", style class "on" when active.
    """

    def __init__(
        self,
        on_label: str = "On",
        off_label: str = "Off",
        active: bool = False,
        on_toggled: Callable[[bool], None] | None = None,
        **kwargs,
    ):
        self._active = active
        self._on_label = on_label
        self._off_label = off_label
        self._on_toggled = on_toggled

        self._label = Label(name="toggle-pill-label")

        super().__init__(name="toggle-pill", child=self._label, **kwargs)

        self._apply_state(emit=False)
        self.connect("clicked", self._handle_click)

    def _apply_state(self, emit: bool = True):
        if self._active:
            self._label.set_label(self._on_label)
            self.add_style_class("on")
        else:
            self._label.set_label(self._off_label)
            self.remove_style_class("on")
        if emit and self._on_toggled:
            self._on_toggled(self._active)

    def _handle_click(self, _):
        self.set_active(not self._active)

    def set_active(self, active: bool):
        if self._active == active:
            return
        self._active = active
        self._apply_state()

    @property
    def active(self) -> bool:
        return self._active
