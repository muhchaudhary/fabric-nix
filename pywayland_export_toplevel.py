import mmap
from typing import List

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


class ClientOutput:
    def __init__(self, client_addresses: List[str]):
        self.client_addresses = client_addresses
        self.shm: WlShmProxy
        self.buff: WlBufferProxy | None = None
        self.display: Display
        self.hyprland_toplevel_export_manager: HyprlandToplevelExportManagerV1Proxy

        self.display = Display()
        self.display.connect()

        registry = self.display.get_registry()  # type: ignore
        registry.dispatcher["global"] = self.registry_global_handler

        self.display.dispatch(block=True)

        self.grab_frame(0)

        while self.display.dispatch(block=True):
            pass

    def shutdown(self) -> None:
        self.display.dispatch()
        self.display.roundtrip()
        self.display.disconnect()

    def registry_global_handler(self, registry, id_, interface, version):
        if interface == "hyprland_toplevel_export_manager_v1":
            self.hyprland_toplevel_export_manager = registry.bind(
                id_, HyprlandToplevelExportManagerV1, version
            )
            print("Got hyprland_toplevel_export_manager_v1")
        elif interface == "wl_shm":
            print("got shm")
            self.shm = registry.bind(id_, WlShm, version)

    def grab_frame(self, idx):
        frame: HyprlandToplevelExportFrameV1Proxy = (
            self.hyprland_toplevel_export_manager.capture_toplevel(
                0, int(self.client_addresses[idx], 16)
            )
        )  # type: ignore
        frame.user_data = idx
        frame.dispatcher["buffer"] = self.create_buffer_for_toplevel
        frame.dispatcher["buffer_done"] = self.on_buffer_done
        frame.dispatcher["flags"] = self.on_buffer_flags
        frame.dispatcher["ready"] = self.on_buffer_ready
        frame.dispatcher["failed"] = self.on_buffer_failed
        # frame.dispatcher["damage"] = lambda *_: print(_)

    def create_buffer_for_toplevel(
        self, _toplevel_export_frame, fmt, width, height, stride
    ) -> int:
        self.width = width
        self.height = height
        self.rowstride = stride

        size = stride * height
        with AnonymousFile(size) as fd:
            self.shm_data = mmap.mmap(
                fd, size, prot=mmap.PROT_READ | mmap.PROT_WRITE, flags=mmap.MAP_SHARED
            )
            pool: WlShmPoolProxy = self.shm.create_pool(fd, size)  # type: ignore
            if self.buff:
                self.buff.destroy()
            self.buff = pool.create_buffer(0, width, height, stride, fmt)  # type: ignore
            pool.destroy()

    def on_buffer_done(self, frame: HyprlandToplevelExportFrameV1Proxy):
        frame.copy(self.buff, 0)

    def on_buffer_ready(self, frame, tv_sec_hi: int, tv_sec_lo: int, tv_nsec: int):
        cario_pixbuf = cairo.ImageSurface(
            cairo.FORMAT_RGB24, self.width, self.height
        ).create_for_data(
            # CAIRO_FORMAT_RGB24 is xrgb
            self.shm_data,
            cairo.FORMAT_RGB24,
            self.width,
            self.height,
            self.rowstride,
        )

        cario_pixbuf.write_to_png(f"test_save_cairo_{frame.user_data}.png")

        print(frame.user_data)

        self.grab_frame(frame.user_data + 1) if frame.user_data != len(
            self.client_addresses
        ) - 1 else self.shutdown()

    def on_buffer_failed(self, *_):
        print("ERROR: failed copy buffer")
        self.shutdown()

    def on_buffer_flags(self, _, flag):
        # print(f"recieved the following flag: {flag}")
        pass


ClientOutput(["279647d0", "279b1760"])
