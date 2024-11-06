from typing import List

from pywayland.client.display import Display
from pywayland.protocol_core.proxy import Proxy
from pywayland.utils import AnonymousFile


# These were generated using:
#  `python -m -i pywayland.scanner -i wayland.xml wlr-foreign-toplevel-management-unstable-v1.xml \
#                  hyprland-toplevel-export-v1.xml xdg-shell.xml wlr-layer-shell-unstable-v1.xml -o protocols`

from protocols.hyprland_toplevel_export_v1.hyprland_toplevel_export_frame_v1 import (
    HyprlandToplevelExportFrameV1Proxy,
)
from protocols.hyprland_toplevel_export_v1.hyprland_toplevel_export_manager_v1 import (
    HyprlandToplevelExportManagerV1,
    HyprlandToplevelExportManagerV1Proxy,
)
from protocols.wayland.wl_buffer import WlBufferProxy
from protocols.wayland.wl_compositor import WlCompositor
from protocols.wayland.wl_shm import WlShm, WlShmProxy
from protocols.wayland.wl_shm_pool import WlShmPoolProxy
from protocols.wayland.wl_surface import WlSurfaceProxy
from protocols.xdg_shell.xdg_surface import XdgSurface
from protocols.xdg_shell.xdg_toplevel import XdgToplevel
from protocols.xdg_shell.xdg_wm_base import XdgWmBase


class ClientOutput:
    def __init__(self, client_addresses: List[str]):
        self.client_addresses = client_addresses
        # THIS IS JANK DO A FIX FOR THIS LATER
        self.last_frame_time = 0

        self.shm: WlShmProxy
        self.buff: WlBufferProxy | None = None
        self.display: Display
        self.surface: WlSurfaceProxy
        self.compositor: Proxy[WlCompositor]
        self.xdg_shell: Proxy[XdgWmBase]
        self.hyprland_toplevel_export_manager: HyprlandToplevelExportManagerV1Proxy

        self.display = Display()
        self.display.connect()
        # print(self.display.get_fd())
        # print("connected to display")
        registry = self.display.get_registry()  # type: ignore
        registry.dispatcher["global"] = self.registry_global_handler

        def shutdown() -> None:
            self.display.dispatch()
            self.display.roundtrip()
            self.display.disconnect()

        self.display.dispatch(block=True)
        self.display.roundtrip()

        self.surface = self.compositor.create_surface()  # type: ignore
        zxdg_surface: Proxy[XdgSurface] = self.xdg_shell.get_xdg_surface(self.surface)  # type: ignore
        zxdg_surface_toplevel: Proxy[XdgToplevel] = zxdg_surface.get_toplevel()  # type: ignore
        zxdg_surface_toplevel.dispatcher["close"] = lambda *_: shutdown()
        # zxdg_surface_toplevel.dispatcher["configure"] = lambda *_: print(_)
        self.surface.commit()  # type: ignore

        frame_callback = self.surface.frame()
        frame_callback.dispatcher["done"] = self.redraw

        self.redraw(frame_callback, self.last_frame_time, destroy_callback=False)

        self.xdg_shell.dispatcher["ping"] = self.shell_ping_handler

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

    def redraw(self, callback, time, destroy_callback=True):
        if destroy_callback:
            callback._destroy()

        # sets the frame rate to 33 ms basically
        if abs(time - self.last_frame_time) < 33 and self.last_frame_time != 0:
            # print("too early...", time - self.last_frame_time)

            callback = self.surface.frame()
            callback.dispatcher["done"] = self.redraw
            # self.surface.commit()
            return
        self.last_frame_time = time

        for address in self.client_addresses:
            self.grab_frame(address)

    def grab_frame(self, address):
        frame: HyprlandToplevelExportFrameV1Proxy = (
            self.hyprland_toplevel_export_manager.capture_toplevel(0, int(address, 16))
        )  # type: ignore
        frame.dispatcher["buffer"] = self.create_buffer_for_toplevel
        frame.dispatcher["buffer_done"] = self.on_buffer_done
        frame.dispatcher["flags"] = self.on_buffer_flags
        frame.dispatcher["ready"] = self.on_buffer_ready
        frame.dispatcher["failed"] = self.on_buffer_failed
        # frame.dispatcher["damage"] = lambda *_: print(_)

    def create_buffer_for_toplevel(
        self, _toplevel_export_frame, fmt, width, height, stride
    ) -> int:
        # print("creating empty buffer with size:", width, height, stride)
        # print(f"buffer format is: {fmt}")

        # print("damaging surface for next update...")
        self.surface.damage_buffer(0, 0, width, height)

        with AnonymousFile(stride * height) as fd:
            # print(" CREATING BUFFER ", fd)
            pool: WlShmPoolProxy = self.shm.create_pool(fd, stride * height)  # type: ignore
            if self.buff:
                self.buff.destroy()
            self.buff = pool.create_buffer(0, width, height, stride, fmt)  # type: ignore
            pool.destroy()

        return 0

    def on_buffer_done(
        self, _toplevel_export_frame: HyprlandToplevelExportFrameV1Proxy
    ):
        _toplevel_export_frame.copy(self.buff, 0)

        # print("starting copy...")

    def on_buffer_ready(self, *_):
        # print("Success! buffer has been copied")
        # print("Preparing surface...")

        self.surface.attach(self.buff, 0, 0)  # type: ignore
        self.surface.commit()  # type: ignore
        # TODO: uncomment this to make it live!
        cbk = self.surface.frame()
        cbk.dispatcher["done"] = self.redraw

    def on_buffer_failed(self, *_):
        print("ERROR: failed copy buffer")

    def on_buffer_flags(self, _, flag):
        # print(f"recieved the following flag: {flag}")
        pass

    def shell_ping_handler(self, xdg_shell, serial):
        print("ping/ponged")
        xdg_shell.pong(serial)


# Replace this with any open client, if you supply it with more than one,
#  the buffers will be on top of eachother so only one will be seen lol
#  this is just to see if you can grab mupltiple toplevels and you can
ClientOutput(["2d4e36c0"])
