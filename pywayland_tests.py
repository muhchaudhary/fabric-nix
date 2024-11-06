from pywayland.client import Display
from pywayland.protocol.wayland import WlBuffer, WlCompositor, WlShm
from pywayland.protocol.wayland.wl_surface import WlSurfaceProxy
from pywayland.utils import AnonymousFile

# These were generated using:
#  `python -m pywayland.scanner wayland.xml wlr-foreign-toplevel-management-unstable-v1.xml hyprland-toplevel-export-v1.xml xdg-shell.xml Downloads/wlr-layer-shell-unstable-v1.xml -o protocols`
from protocols.hyprland_toplevel_export_v1 import HyprlandToplevelExportManagerV1
from protocols.hyprland_toplevel_export_v1.hyprland_toplevel_export_frame_v1 import (
    HyprlandToplevelExportFrameV1Proxy,
)
from protocols.xdg_shell.xdg_surface import XdgSurfaceProxy
from protocols.xdg_shell.xdg_toplevel import XdgToplevelProxy
from protocols.xdg_shell.xdg_wm_base import XdgWmBase, XdgWmBaseProxy


class ClientOutput:
    def __init__(self, client_address: str):
        self.client_address = client_address

        self.shm: WlShm = None
        self.buff: WlBuffer = None
        self.display: Display = None
        self.surface: WlSurfaceProxy = None
        self.compositor: WlCompositor = None
        self.xdg_shell: XdgWmBaseProxy = None
        self.hyprland_toplevel_export_manager: HyprlandToplevelExportManagerV1 = None

        self.display = Display()
        self.display.connect()
        # print(self.display.get_fd())
        print("connected to display")
        registry = self.display.get_registry()
        registry.dispatcher["global"] = self.registry_global_handler

        def shutdown() -> None:
            self.display.dispatch()
            self.display.roundtrip()
            self.display.disconnect()

        self.display.dispatch(block=True)
        self.display.roundtrip()

        self.surface = self.compositor.create_surface()
        zxdg_surface: XdgSurfaceProxy = self.xdg_shell.get_xdg_surface(self.surface)
        zxdg_surface_toplevel: XdgToplevelProxy = zxdg_surface.get_toplevel()
        zxdg_surface_toplevel.dispatcher["close"] = lambda *_: shutdown()
        # zxdg_surface_toplevel.dispatcher["configure"] = lambda *_: print(_)
        self.surface.commit()

        self.xdg_shell.dispatcher["ping"] = self.shell_ping_handler

        frame: HyprlandToplevelExportFrameV1Proxy = (
            self.hyprland_toplevel_export_manager.capture_toplevel(
                0, int(self.client_address, 16)
            )
        )
        print()
        frame.dispatcher["buffer"] = self.create_buffer_for_toplevel
        frame.dispatcher["buffer_done"] = self.on_buffer_done

        frame.dispatcher["flags"] = self.on_buffer_flags
        frame.dispatcher["ready"] = self.on_buffer_ready
        frame.dispatcher["failed"] = self.on_buffer_failed

        while self.display.dispatch(block=True) != -1:
            pass

    def registry_global_handler(self, registry, id_, interface, version):
        if interface == "xdg_wm_base":
            self.xdg_shell = registry.bind(id_, XdgWmBase, version)
            print("got xdg_wm_base")
        if interface == "wl_compositor":
            print("got compositor")
            self.compositor = registry.bind(id_, WlCompositor, version)
        if interface == "hyprland_toplevel_export_manager_v1":
            self.hyprland_toplevel_export_manager = registry.bind(
                id_, HyprlandToplevelExportManagerV1, version
            )
            print("Got hyprland_toplevel_export_manager_v1")
        elif interface == "wl_shm":
            print("got shm")
            self.shm = registry.bind(id_, WlShm, version)

    def create_buffer_for_toplevel(
        self, _toplevel_export_frame, fmt, width, height, stride
    ) -> int:
        print("creating empty buffer with size:", fmt, width, height, stride)
        with AnonymousFile(stride * height) as fd:
            pool = self.shm.create_pool(fd, stride * height)
            self.buff = pool.create_buffer(0, width, height, stride, fmt)
            pool.destroy()

        return 0

    def on_buffer_done(
        self, _toplevel_export_frame: HyprlandToplevelExportFrameV1Proxy
    ):
        _toplevel_export_frame.copy(self.buff, 0)
        print("starting copy...")

    def on_buffer_ready(self, *_):
        print("Success! buffer has been copied")
        print("Preparing surface...")

        # self.display.roundtrip()

        self.surface.attach(self.buff, 0, 0)
        self.surface.commit()

    def on_buffer_failed(self, *_):
        print("ERROR: failed copy buffer")

    def on_buffer_flags(self, _, flag):
        print(f"recieved the following flag: {flag}")

    def shell_ping_handler(self, xdg_shell, serial):
        print("ping/ponged")
        xdg_shell.pong(serial)


# Replace this with any open client
ClientOutput("271bbe50")
