from typing import Literal

from fabric_config.utils.hyprland_monitor import get_hyprland_monitors
from gi.repository import GLib, Gdk

from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow
from fabric.widgets.widget import Widget


# Greatly inspired by:
#   CREDIT TO AYLUR: https://github.com/Aylur/dotfiles/blob/main/ags/widget/PopupWindow.ts


class Padding(EventBox):
    def __init__(self, name: str | None = None, style: str = "", **kwargs):
        super().__init__(
            name=name,
            h_expand=True,
            v_expand=True,
            child=Box(style=style, h_expand=True, v_expand=True),
            events=["button-press"],
            **kwargs,
        )
        self.set_can_focus(False)


class PopupRevealer(EventBox):
    def __init__(
        self,
        popup_window: WaylandWindow,
        decorations: str = "padding: 1px;",
        name: str | None = None,
        child: Widget | None = None,
        transition_type: Literal[
            "none",
            "crossfade",
            "slide-right",
            "slide-left",
            "slide-up",
            "slide-down",
        ] = "slide-down",
        transition_duration: int = 400,
    ):
        self.revealer: Revealer = Revealer(
            h_expand=True,
            v_expand=True,
            name=name,
            child=child,
            transition_type=transition_type,
            transition_duration=transition_duration,
            notify_child_revealed=lambda revealer, _: (
                [
                    revealer.hide(),
                    popup_window.set_visible(False),
                ]
                if not revealer.fully_revealed
                else None
            ),
            notify_reveal_child=lambda revealer, _: (
                [
                    popup_window.set_visible(True),
                ]
                if revealer.child_revealed
                else None
            ),
        )
        super().__init__(
            style=decorations,
            child=self.revealer,
        )


def make_layout(anchor: str, name: str, popup: PopupRevealer, **kwargs) -> Box:
    match anchor:
        case "center-left":
            return Box(
                children=[
                    Box(
                        orientation="vertical",
                        children=[
                            Padding(name=name, **kwargs),
                            popup,
                            Padding(name=name, **kwargs),
                        ],
                    ),
                    Padding(name=name, **kwargs),
                ]
            )

        case "center":
            return Box(
                children=[
                    Padding(name=name, **kwargs),
                    Box(
                        orientation="vertical",
                        children=[
                            Padding(name=name, **kwargs),
                            popup,
                            Padding(name=name, **kwargs),
                        ],
                    ),
                    Padding(name=name, **kwargs),
                ]
            )
        case "center-right":
            return Box(
                children=[
                    Padding(name=name, **kwargs),
                    Box(
                        orientation="vertical",
                        children=[
                            Padding(name=name, **kwargs),
                            popup,
                            Padding(name=name, **kwargs),
                        ],
                    ),
                ]
            )
        case "top":
            return Box(
                children=[
                    Padding(name=name, **kwargs),
                    Box(
                        orientation="vertical",
                        children=[popup, Padding(name=name, **kwargs)],
                    ),
                    Padding(name=name, **kwargs),
                ]
            )
        case "top-right":
            return Box(
                children=[
                    Padding(name=name, **kwargs),
                    Box(
                        h_expand=False,
                        orientation="vertical",
                        children=[popup, Padding(name=name, **kwargs)],
                    ),
                ]
            )
        case "top-center":
            return Box(
                children=[
                    Padding(name=name, **kwargs),
                    Box(
                        h_expand=False,
                        orientation="vertical",
                        children=[popup, Padding(name=name, **kwargs)],
                    ),
                    Padding(name=name, **kwargs),
                ]
            )
        case "top-left":
            return Box(
                children=[
                    Box(
                        h_expand=False,
                        orientation="vertical",
                        children=[popup, Padding(name=name, **kwargs)],
                    ),
                    Padding(name=name, **kwargs),
                ]
            )
        case "bottom-left":
            return Box(
                children=[
                    Box(
                        h_expand=False,
                        orientation="vertical",
                        children=[Padding(name=name, **kwargs), popup],
                    ),
                    Padding(name=name, **kwargs),
                ]
            )
        case "bottom-center":
            return Box(
                children=[
                    Padding(name=name, **kwargs),
                    Box(
                        h_expand=False,
                        orientation="vertical",
                        children=[Padding(name=name, **kwargs), popup],
                    ),
                    Padding(name=name, **kwargs),
                ]
            )
        case "bottom-right":
            return Box(
                children=[
                    Padding(name=name, **kwargs),
                    Box(
                        h_expand=True,
                        orientation="vertical",
                        children=[Padding(name=name, **kwargs), popup],
                    ),
                ]
            )
        case _:
            raise ValueError(f"unknown popup anchor: {anchor!r}")


class PopupWindow(WaylandWindow):
    def __init__(
        self,
        layer: Literal["background", "bottom", "top", "overlay"] = "top",
        name: str = "popup-window",
        decorations: str = "padding: 1px;",
        child: Widget | None = None,
        transition_type: Literal[
            "none",
            "crossfade",
            "slide-right",
            "slide-left",
            "slide-up",
            "slide-down",
        ] = "slide-down",
        transition_duration: int = 100,
        popup_visible: bool = False,
        anchor: Literal[
            "center-left",
            "center",
            "center-right",
            "top",
            "top-right",
            "top-center",
            "top-left",
            "bottom-left",
            "bottom-center",
            "bottom-right",
        ] = "top-right",
        enable_inhibitor: bool = False,
        keyboard_mode: Literal["none", "exclusive", "on-demand"] = "on-demand",
        timeout: int = 1000,
        # the layer-shell namespace (fabric sets it from the title); Hyprland's
        # layer rules match it, e.g. to blur behind popups
        namespace: str = "fabric-popup",
    ):
        self._layer = layer
        # (not _anchor: WaylandWindow keeps its layer-shell anchor there)
        self._popup_anchor = anchor
        self._placed_under: Widget | None = None
        self.timeout = timeout
        self.currtimeout = 0
        self.popup_running = False

        self.popup_visible = popup_visible

        self.enable_inhibitor = enable_inhibitor

        self.monitor_number: int | None = None
        self.hyprland_monitor = get_hyprland_monitors()

        self.reveal_child = PopupRevealer(
            name=name,
            popup_window=self,
            child=child,
            transition_type=transition_type,
            transition_duration=transition_duration,
            decorations=decorations,
        )

        super().__init__(
            title=namespace,
            layer=self._layer,
            keyboard_mode=keyboard_mode,
            visible=False,
            exclusivity="normal",
            anchor="top bottom right left",
            child=make_layout(
                anchor=anchor,
                name=name,
                popup=self.reveal_child,
                on_button_press_event=self.on_inhibit_click,
            ),
            on_key_release_event=self.on_key_release,
        )

    def place_under(self, widget: Widget, edge_gap: int = 6):
        """
        Centre a top-left or top-right popup under `widget` (a bar button),
        kept `edge_gap` px clear of the screen's sides. The popup's window
        spans the monitor like the bar, so bar coordinates are screen ones.
        Placed again once the content is laid out, when its width is known.
        """
        self._placed_under = widget
        self._edge_gap = edge_gap
        content = self.reveal_child.revealer.get_child()
        if content is not None and not getattr(self, "_placing_hooked", False):
            self._placing_hooked = True
            content.connect(
                "size-allocate",
                # not during allocation: changing a margin there re-queues it
                lambda *_: GLib.idle_add(lambda: self._place() or False),
            )
        self._place()

    def _place(self):
        widget = self._placed_under
        if widget is None:
            return
        toplevel = widget.get_toplevel()
        coords = widget.translate_coordinates(
            toplevel, widget.get_allocated_width() // 2, 0
        )
        if coords is None:
            return
        center = coords[0]
        screen = toplevel.get_allocated_width()
        # the content's laid-out width once it's showing; its preferred one
        # before (the revealer is hidden while the popup's closed)
        content = self.reveal_child.revealer.get_child() or self.reveal_child
        width = content.get_allocated_width()
        if width <= 1:
            width = content.get_preferred_width()[1]
        width += 2  # PopupRevealer's decoration padding, either side
        left = round(center - width / 2)
        left = max(self._edge_gap, min(left, screen - width - self._edge_gap))
        if self._popup_anchor == "top-right":
            margin = max(0, screen - left - width)
            if self.reveal_child.get_margin_end() != margin:
                self.reveal_child.set_margin_end(margin)
        elif self._popup_anchor == "top-left":
            margin = max(0, left)
            if self.reveal_child.get_margin_start() != margin:
                self.reveal_child.set_margin_start(margin)

    def on_key_release(self, _, event_key: Gdk.EventKey):
        if event_key.keyval == Gdk.KEY_Escape:
            self.popup_visible = False
            self.reveal_child.revealer.set_reveal_child(self.popup_visible)

    def on_inhibit_click(self, *_):
        self.popup_visible = False
        self.reveal_child.revealer.set_reveal_child(self.popup_visible)

    def toggle_popup(self, monitor: bool = False):
        if monitor:
            curr_monitor = self.hyprland_monitor.get_current_gdk_monitor_id()
            self.monitor = curr_monitor
            if self.monitor_number != curr_monitor and self.popup_visible:
                self.monitor_number = curr_monitor
                return

            self.monitor_number = curr_monitor

        if not self.popup_visible:
            self.reveal_child.revealer.show()

        self.set_property("pass-through", not self.enable_inhibitor)
        self.popup_visible = not self.popup_visible
        self.reveal_child.revealer.set_reveal_child(self.popup_visible)

    def popup_timeout(self):
        curr_monitor = self.hyprland_monitor.get_current_gdk_monitor_id()
        self.monitor = curr_monitor

        if not self.popup_visible:
            self.reveal_child.revealer.show()
        if self.popup_running:
            self.currtimeout = 0
            return
        self.popup_visible = True
        self.reveal_child.revealer.set_reveal_child(self.popup_visible)
        self.popup_running = True

        def popup_func():
            if self.currtimeout >= self.timeout:
                self.popup_visible = False
                self.reveal_child.revealer.set_reveal_child(self.popup_visible)
                self.currtimeout = 0
                self.popup_running = False
                return False
            self.currtimeout += 500
            return True

        self.set_property("pass-through", not self.enable_inhibitor)
        GLib.timeout_add(500, popup_func)
