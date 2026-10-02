import gi
from collections.abc import Callable

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402


class ToggleSwitch(Gtk.Switch):
    """iOS-style toggle switch wrapping Gtk.Switch.

    CSS node: switch / switch slider
    """

    def __init__(
        self,
        active: bool = False,
        on_toggled: Callable[[bool], None] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._on_toggled = on_toggled
        self.set_active(active)
        self.connect("state-set", self._handle_state_set)
        self.show()

    def _handle_state_set(self, _, state: bool) -> bool:
        if self._on_toggled:
            self._on_toggled(state)
        return False  # let GTK update the state normally
