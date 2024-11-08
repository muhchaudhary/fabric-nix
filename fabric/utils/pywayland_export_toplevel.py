import mmap

import cairo
from pywayland.client.display import Display
from pywayland.utils import AnonymousFile

# These were generated using:
#  `python -m -i pywayland.scanner -i wayland.xml hyprland-toplevel-export-v1.xml -o protocols`
from protocols.hyprland_toplevel_export_v1.hyprland_toplevel_export_frame_v1 import (
    HyprlandToplevelExportFrameV1Proxy,
)
from protocols.hyprland_toplevel_export_v1.hyprland_toplevel_export_manager_v1 import (
    HyprlandToplevelExportManagerV1,
    HyprlandToplevelExportManagerV1Proxy,
)
from protocols.wayland.wl_buffer import WlBufferProxy
from protocols.wayland.wl_shm import WlShm, WlShmProxy
from protocols.wayland.wl_shm_pool import WlShmPoolProxy

from fabric.core.service import Service, Signal


import gi

gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GdkPixbuf


class ClientOutput(Service):
    @Signal
    def frame_ready(self, address: str, pixbuf: GdkPixbuf.Pixbuf) -> None: ...

    def __init__(self):
        super().__init__()
        self.roundtrip_needed = True
        self.shm: WlShmProxy
        self.hyprland_toplevel_export_manager: HyprlandToplevelExportManagerV1Proxy

    def grab_frame_for_address(self, hyprland_address: str):
        with Display() as display:
            self.roundtrip_needed = True
            registry = display.get_registry()  # type: ignore
            registry.dispatcher["global"] = self.registry_global_handler
            display.dispatch()
            display.roundtrip()
            self._grab_frame(hyprland_address)
            while self.roundtrip_needed:
                display.roundtrip()

    def shutdown(self) -> None:
        self.roundtrip_needed = False

    def registry_global_handler(self, registry, id_, interface, version):
        if interface == "hyprland_toplevel_export_manager_v1":
            self.hyprland_toplevel_export_manager = registry.bind(
                id_, HyprlandToplevelExportManagerV1, version
            )
        elif interface == "wl_shm":
            self.shm = registry.bind(id_, WlShm, version)

    def _grab_frame(self, hyprland_address: str):
        # print("begin grab frame...")
        frame: HyprlandToplevelExportFrameV1Proxy = (
            self.hyprland_toplevel_export_manager.capture_toplevel(
                0, int(hyprland_address, 16)
            )
        )  # type: ignore
        frame.user_data = [hyprland_address]
        frame.dispatcher["buffer"] = self.create_buffer_for_toplevel
        frame.dispatcher["buffer_done"] = self.on_buffer_done
        frame.dispatcher["ready"] = self.on_buffer_ready
        frame.dispatcher["failed"] = self.on_buffer_failed
        # frame.dispatcher["damage"] = lambda *_: print(_)

    def create_buffer_for_toplevel(self, frame, fmt, width, height, stride):
        # print("creating buffer...")
        self.width = width
        self.height = height
        self.rowstride = stride

        size = stride * height
        with AnonymousFile(size) as fd:
            shm_data = mmap.mmap(
                fd, size, prot=mmap.PROT_READ | mmap.PROT_WRITE, flags=mmap.MAP_SHARED
            )
            pool: WlShmPoolProxy = self.shm.create_pool(fd, size)  # type: ignore
            buff = pool.create_buffer(0, width, height, stride, fmt)  # type: ignore
            pool.destroy()
            frame.user_data.extend([buff, shm_data])
        return 0

    def on_buffer_done(self, frame: HyprlandToplevelExportFrameV1Proxy):
        buff: WlBufferProxy = frame.user_data[1]
        frame.copy(buff, 0)

    def on_buffer_ready(self, frame, tv_sec_hi: int, tv_sec_lo: int, tv_nsec: int):
        buff: WlBufferProxy = frame.user_data[1]
        shm_data: mmap.mmap = frame.user_data[2]

        # CAIRO_FORMAT_RGB24 is xrgb
        pixbuf: GdkPixbuf.Pixbuf = Gdk.pixbuf_get_from_surface(
            cairo.ImageSurface.create_for_data(
                shm_data,  # type: ignore
                cairo.FORMAT_RGB24,
                self.width,
                self.height,
                self.rowstride,
            ),
            0,
            0,
            self.width,
            self.height,
        )

        buff.destroy()
        shm_data.close()
        self.emit("frame-ready", frame.user_data[0], pixbuf)
        self.shutdown()
        frame.destroy()

    def on_buffer_failed(self, frame: HyprlandToplevelExportFrameV1Proxy):
        print("ERROR: failed copy buffer")
        frame.user_data[1].destroy()
        frame.destroy()
