"""
Hand ("pointer") cursor over everything clickable.

GTK3 ignores the CSS `cursor` property, so this hooks the enter signal for
every widget once, app-wide: when the pointer enters a button, switch or
slider, the window it entered gets the pointer cursor. Buttons have their
own input window, so the cursor reverts by itself when the pointer leaves.
Other clickable widgets (e.g. an EventBox you can click) opt in with the
`clickable` style class. Custom-drawn widgets (the desktop music card, seek
bars) set their own cursors.
"""

from gi.repository import Gdk, GObject, Gtk

# widgets that act on click; subclasses (toggle, link, menu buttons…) included
CLICKABLE = (Gtk.Button, Gtk.Switch, Gtk.Scale)

_cursors: dict[Gdk.Display, Gdk.Cursor] = {}
_installed = False


def _pointer(display: Gdk.Display) -> Gdk.Cursor | None:
    cursor = _cursors.get(display)
    if cursor is None:
        cursor = Gdk.Cursor.new_from_name(display, "pointer")
        if cursor is None:
            return None
        _cursors[display] = cursor
    return cursor


def _is_clickable(widget: Gtk.Widget) -> bool:
    return isinstance(widget, CLICKABLE) or widget.get_style_context().has_class(
        "clickable"
    )


def _on_enter(widget: Gtk.Widget, event: Gdk.EventCrossing, *_) -> bool:
    if _is_clickable(widget) and widget.get_sensitive():
        window = event.window
        if window is not None and window.get_cursor() is None:
            cursor = _pointer(window.get_display())
            if cursor is not None:
                window.set_cursor(cursor)
    return True  # keep the hook installed


def install_pointer_cursors():
    """Call once, before the windows are built."""
    global _installed
    if _installed:
        return
    GObject.add_emission_hook(Gtk.Widget, "enter-notify-event", _on_enter)
    _installed = True
