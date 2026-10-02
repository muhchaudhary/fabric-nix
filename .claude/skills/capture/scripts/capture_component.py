"""
Render a Fabric component to a PNG without screenshotting the screen.

Runs the component in its own short-lived Fabric application (separate from the
running bar), compiles the project's SCSS for the chosen theme, waits for async
content (thumbnails, previews) to settle, then draws the widget with cairo.

    python .claude/skills/capture/scripts/capture_component.py \
        fabric_config.components.overview:Overview --theme dark --scale 2

TARGET is `module:attribute`. A class is instantiated with no arguments; an
instance is used as-is. PopupWindow targets are opened with toggle_popup() and
their revealed content is captured; other windows have their child captured; a
bare widget is placed in a window first.
"""

import argparse
import importlib
import os
import shutil
import subprocess
import sys
import tempfile

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
sys.path.insert(0, PROJECT_ROOT)

import cairo  # noqa: E402
import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

DEFAULT_OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "captures")
BACKGROUNDS = {"dark": (0.12, 0.12, 0.16), "light": (0.85, 0.86, 0.90)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "target",
        help="module:attribute, e.g. fabric_config.components.overview:Overview",
    )
    parser.add_argument(
        "-o", "--out", help="output PNG (default: captures/<attribute>-<theme>.png)"
    )
    parser.add_argument("--theme", choices=["dark", "light"], default="dark")
    parser.add_argument(
        "--delay",
        type=int,
        default=2500,
        help="ms to wait before capturing (async content)",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="render scale, e.g. 2 for HiDPI-sharp output",
    )
    parser.add_argument(
        "--eval", dest="setup", help="python run before capture; `obj` is the target"
    )
    parser.add_argument("--transparent", action="store_true", help="no background fill")
    parser.add_argument(
        "--screen",
        action="store_true",
        help="photograph the real on-screen pixels with grim instead of drawing "
        "offscreen (exact, incl. scrolled content; needs a visible surface)",
    )
    return parser.parse_args()


def compile_css(theme: str) -> str:
    style_dir = os.path.join(PROJECT_ROOT, "fabric_config", "style")
    scss = os.path.join(
        style_dir, "main-light.scss" if theme == "light" else "main.scss"
    )
    css = os.path.join(tempfile.gettempdir(), f"fabric-capture-{os.getpid()}.css")
    subprocess.run(["sass", "--no-source-map", scss, css], check=True)
    return css


def find_grim() -> str:
    grim = shutil.which("grim")
    if grim:
        return grim
    out = subprocess.run(
        ["nix", "build", "--no-link", "--print-out-paths", "nixpkgs#grim"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return os.path.join(out, "bin", "grim")


def surface_origin(toplevel: Gtk.Widget) -> tuple[int, int] | None:
    import json

    try:
        layers = json.loads(
            subprocess.run(
                ["hyprctl", "layers", "-j"], capture_output=True, text=True, check=True
            ).stdout
        )
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None
    size = (toplevel.get_allocated_width(), toplevel.get_allocated_height())
    for monitor in layers.values():
        for level in monitor["levels"].values():
            for layer in level:
                if layer["pid"] == os.getpid() and (layer["w"], layer["h"]) == size:
                    return layer["x"], layer["y"]
    return None


def grab_screen(widget: Gtk.Widget, out: str):
    """
    Screenshot the widget's on-screen rectangle. Offscreen widget.draw()
    mis-renders scrolled content (viewports draw with a stale offset), so this
    is the faithful mode. GTK can't see where a layer-shell surface sits (it
    may start below the bar's exclusive zone), so ask Hyprland for this
    process's surface of the toplevel's size; fall back to the monitor origin.
    """
    toplevel = widget.get_toplevel()
    x, y = widget.translate_coordinates(toplevel, 0, 0)
    alloc = widget.get_allocation()
    origin = surface_origin(toplevel)
    if origin is None:
        geo = (
            widget.get_display()
            .get_monitor_at_window(toplevel.get_window())
            .get_geometry()
        )
        origin = (geo.x, geo.y)
    region = f"{origin[0] + x},{origin[1] + y} {alloc.width}x{alloc.height}"
    subprocess.run([find_grim(), "-g", region, out], check=True)


def resolve_target(spec: str):
    module_name, _, attr = spec.partition(":")
    if not attr:
        sys.exit(f"TARGET must be module:attribute, got {spec!r}")
    obj = getattr(importlib.import_module(module_name), attr)
    return (obj() if isinstance(obj, type) else obj), attr


def main():
    args = parse_args()
    css = compile_css(args.theme)

    from fabric import Application
    from fabric.widgets.wayland import WaylandWindow

    from fabric_config.widgets.popup_window_v2 import PopupWindow

    obj, attr = resolve_target(args.target)

    if isinstance(obj, PopupWindow):
        window = obj

        def open_and_get():
            obj.toggle_popup()
            return obj.reveal_child.revealer.get_child()

    elif isinstance(obj, Gtk.Window):
        window = obj

        def open_and_get():
            obj.show()  # not show_all(): keep intentionally hidden widgets hidden
            return obj.get_child()

    elif isinstance(obj, Gtk.Widget):
        window = WaylandWindow(
            layer="overlay", anchor="center", child=obj, visible=False
        )

        def open_and_get():
            window.show()
            return obj

    else:
        sys.exit(f"{args.target} is not a GTK widget or window ({type(obj).__name__})")

    # a unique name so this never clashes with the running bar's DBus name
    app = Application(f"fabric-capture-{os.getpid()}", window)
    app.set_stylesheet_from_file(css)

    out = args.out or os.path.join(DEFAULT_OUT_DIR, f"{attr}-{args.theme}.png")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    state = {}

    def start():
        state["widget"] = open_and_get()
        if args.setup:
            exec(args.setup, {"obj": obj, "widget": state["widget"], "GLib": GLib})
        GLib.timeout_add(args.delay, snap)
        return False

    def snap():
        widget = state["widget"]
        alloc = widget.get_allocation()
        if alloc.width <= 1 or alloc.height <= 1:
            print(
                f"error: widget has no size ({alloc.width}x{alloc.height}); is it visible?",
                file=sys.stderr,
            )
            app.quit()
            return False
        if args.screen:
            grab_screen(widget, out)
            print(
                f"captured {alloc.width}x{alloc.height} (screen) -> {os.path.abspath(out)}"
            )
            app.quit()
            return False
        width, height = (
            round(alloc.width * args.scale),
            round(alloc.height * args.scale),
        )
        surface = cairo.ImageSurface(cairo.Format.ARGB32, width, height)
        cr = cairo.Context(surface)
        cr.scale(args.scale, args.scale)
        if not args.transparent:
            cr.set_source_rgb(*BACKGROUNDS[args.theme])
            cr.paint()
        widget.draw(cr)
        surface.write_to_png(out)
        print(
            f"captured {alloc.width}x{alloc.height} (x{args.scale}) -> {os.path.abspath(out)}"
        )
        app.quit()
        return False

    GLib.timeout_add(300, start)
    # safety net so a stuck capture never leaves a window up
    GLib.timeout_add(args.delay + 15000, lambda: app.quit() or False)
    app.run()
    try:
        os.remove(css)
    except OSError:
        pass


if __name__ == "__main__":
    main()
