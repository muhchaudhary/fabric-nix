from gi.repository import Gtk, GtkLayerShell, GLib
from fabric.widgets.wayland import WaylandWindow
from fabric_config.utils.hyprland_monitor import get_hyprland_monitors


class PopupWindow(WaylandWindow):
    def __init__(
        self,
        parent: WaylandWindow,
        pointing_to: Gtk.Widget | None = None,
        margin: tuple[int, ...] | str = "0px 0px 0px 0px",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.exclusivity = "none"
        self._is_centered = False
        self._parent = parent
        self._pointing_widget = pointing_to
        self._hyprland = get_hyprland_monitors()
        self._base_margin = self.extract_margin(margin)
        self.margin = self._base_margin.values()

        self.connect("notify::visible", self.do_update_handlers)

    def get_coords_for_widget(self, widget: Gtk.Widget) -> tuple[int, int]:
        if not ((toplevel := widget.get_toplevel()) and toplevel.is_toplevel()):  # type: ignore
            return 0, 0
        allocation = widget.get_allocation()
        x, y = widget.translate_coordinates(toplevel, allocation.x, allocation.y) or (
            0,
            0,
        )
        return round(x / 2), round(y / 2)

    def set_pointing_to(self, widget: Gtk.Widget | None):
        if self._pointing_widget:
            try:
                self._pointing_widget.disconnect_by_func(self.do_handle_size_allocate)
            except Exception:
                pass
        self._pointing_widget = widget
        return self.do_update_handlers()

    def animate_pointing_to(self, widget: Gtk.Widget, duration_ms: int = 150):
        if not self.get_visible():
            self.set_pointing_to(widget)
            return

        anim_id: int | None = getattr(self, "_anim_id", None)
        if anim_id is not None:
            GLib.source_remove(anim_id)
            self._anim_id = None

        try:
            start_margin = tuple(self.margin)
        except Exception:
            self.set_pointing_to(widget)
            return

        # Purge ALL stacked size-allocate handlers (do_update_handlers stacks them)
        for w in filter(None, [self._pointing_widget, self]):
            while True:
                try:
                    w.disconnect_by_func(self.do_handle_size_allocate)
                except Exception:
                    break

        self._pointing_widget = widget
        self._animating = True
        self.do_reposition(self.do_calculate_edges())
        target_margin = tuple(self.margin)

        if start_margin == target_margin:
            self._animating = False
            widget.connect("size-allocate", self.do_handle_size_allocate)
            self.connect("size-allocate", self.do_handle_size_allocate)
            return

        self.margin = start_margin
        start_us = GLib.get_monotonic_time()
        duration_us = duration_ms * 1000

        def tick():
            t = min((GLib.get_monotonic_time() - start_us) / duration_us, 1.0)
            ease = 1.0 - (1.0 - t) ** 2  # ease-out quad
            # Recompute target each tick so popup size changes (new image loading)
            # are tracked — at t=1.0 ease=1.0 so we land exactly on live_target.
            self.do_reposition(self.do_calculate_edges())
            live_target = tuple(self.margin)
            self.margin = tuple(
                round(a + (b - a) * ease) for a, b in zip(start_margin, live_target)
            )
            if t >= 1.0:
                self._anim_id = None
                self._animating = False
                widget.connect("size-allocate", self.do_handle_size_allocate)
                self.connect("size-allocate", self.do_handle_size_allocate)
                return False
            return True

        self._anim_id = GLib.timeout_add(16, tick)

    def do_update_handlers(self, *_):
        if not self._pointing_widget:
            return

        if not self.get_visible():
            try:
                self._pointing_widget.disconnect_by_func(self.do_handle_size_allocate)
                self.disconnect_by_func(self.do_handle_size_allocate)
            except Exception:
                pass
            return

        self._pointing_widget.connect("size-allocate", self.do_handle_size_allocate)
        self.connect("size-allocate", self.do_handle_size_allocate)

        return self.do_handle_size_allocate()

    def do_handle_size_allocate(self, *_):
        if getattr(self, "_animating", False):
            return
        return self.do_reposition(self.do_calculate_edges())

    def do_calculate_edges(self):
        parent_anchor = self._parent.anchor
        has_left = GtkLayerShell.Edge.LEFT in parent_anchor
        has_right = GtkLayerShell.Edge.RIGHT in parent_anchor
        has_top = GtkLayerShell.Edge.TOP in parent_anchor
        has_bottom = GtkLayerShell.Edge.BOTTOM in parent_anchor

        if has_left and has_right:
            # Full-width horizontal bar
            self.anchor = "left top" if has_top else "left bottom"
            self._is_centered = False
            return "x"

        if has_top and has_bottom:
            # Full-height vertical bar
            self.anchor = "top right" if has_right else "top left"
            self._is_centered = False
            return "y"

        if has_left or has_right:
            # Partial-width dock anchored to one side (e.g. bottom-left, bottom-right)
            self.anchor = "left top" if has_top else "left bottom"
            self._is_centered = False
            return "x"

        # Floating / no explicit x-anchor → center over the widget
        self.anchor = "left bottom"
        self._is_centered = True
        return "x"

    def do_reposition(self, move_axe: str):
        parent_margin = self._parent.margin
        parent_x_margin, parent_y_margin = parent_margin[0], parent_margin[3]

        height = self.get_allocated_height()
        width = self.get_allocated_width()

        if self._pointing_widget:
            coords = self.get_coords_for_widget(self._pointing_widget)
            coords_centered = (
                round(coords[0] + self._pointing_widget.get_allocated_width() / 2),
                round(coords[1] + self._pointing_widget.get_allocated_height() / 2),
            )
        else:
            coords_centered = (
                round(self._parent.get_allocated_width() / 2),
                round(self._parent.get_allocated_height() / 2),
            )

        if self._is_centered:
            # center on the focused monitor; if it can't be resolved, fall back
            # to centering on the parent
            monitor_id = self._hyprland.get_current_gdk_monitor_id()
            monitor = (
                self._hyprland.display.get_monitor(monitor_id)
                if monitor_id is not None
                else None
            )
            parent_width = self._parent.get_allocated_width()
            monitor_width = (
                monitor.get_geometry().width if monitor is not None else parent_width
            )
            self.margin = tuple(
                a + b
                for a, b in zip(
                    (
                        0,
                        0,
                        0,
                        (monitor_width / 2 - parent_width / 2)
                        - width / 2
                        + coords_centered[0],
                    ),
                    self._base_margin.values(),
                )
            )
            return

        self.margin = tuple(
            a + b
            for a, b in zip(
                (
                    (
                        0,
                        0,
                        0,
                        round((parent_x_margin + coords_centered[0]) - (width / 2)),
                    )
                    if move_axe == "x"
                    else (
                        round((parent_y_margin + coords_centered[1]) - (height / 2)),
                        0,
                        0,
                        0,
                    )
                ),
                self._base_margin.values(),
            )
        )
