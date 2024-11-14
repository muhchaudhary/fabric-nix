from io import BytesIO
import mmap

import cairo
import gi
from loguru import logger

# These were generated using:
#  `python -m -i pywayland.scanner -i wayland.xml hyprland-toplevel-export-v1.xml -o protocols`

from pywayland.protocol.hyprland_toplevel_export_v1.hyprland_toplevel_export_frame_v1 import (
    HyprlandToplevelExportFrameV1Proxy,
)


from pywayland.protocol.hyprland_toplevel_export_v1.hyprland_toplevel_export_manager_v1 import (
    HyprlandToplevelExportManagerV1,
    HyprlandToplevelExportManagerV1Proxy,
)

from pywayland.protocol.wayland.wl_buffer import WlBufferProxy
from pywayland.protocol.wayland.wl_shm import WlShm, WlShmProxy
from pywayland.protocol.wayland.wl_shm_pool import WlShmPoolProxy

from pywayland.client.display import Display
from pywayland.utils import AnonymousFile

from fabric.core.service import Service, Signal

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf


class ClientOutput(Service):
    @Signal
    def frame_ready(self, address: str, pixbuf: GdkPixbuf.Pixbuf) -> None: ...

    def __init__(self):
        super().__init__()
        self.shm: WlShmProxy | None = None
        self.hyprland_toplevel_export_manager: (
            HyprlandToplevelExportManagerV1Proxy | None
        ) = None

        self.display = Display()
        self.display.connect()
        registry = self.display.get_registry()  # type: ignore
        registry.dispatcher["global"] = self.registry_global_handler
        self.display.dispatch(block=True)

    def grab_frame_for_address(self, hyprland_address: str):
        # Only grab frame once display is ready
        logger.info(f"Grabbing Frame: {hyprland_address}")
        if self.shm and self.hyprland_toplevel_export_manager:
            return self._grab_frame(hyprland_address)
        logger.error(
            "[PyWayland] Could not grab frame. Is hyprland-toplevel-export supported?"
        )

    def registry_global_handler(self, registry, id_, interface, version):
        if interface == "hyprland_toplevel_export_manager_v1":
            self.hyprland_toplevel_export_manager = registry.bind(
                id_, HyprlandToplevelExportManagerV1, version
            )
            logger.info("[PyWayland] grabbed hyprland_toplevel_export_manager_v1")
        elif interface == "wl_shm":
            self.shm = registry.bind(id_, WlShm, version)
            logger.info("[PyWayland] grabbed wl_shm")

    def _grab_frame(self, hyprland_address: str):
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
        self.display.roundtrip()
        # frame.dispatcher["damage"] = lambda *_: print(_)

    def create_buffer_for_toplevel(self, frame, fmt, width, height, stride):
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
        self.display.roundtrip()
        # To get to on_buffer_ready
        self.display.dispatch(block=True)

    def on_buffer_ready(self, frame, tv_sec_hi: int, tv_sec_lo: int, tv_nsec: int):
        buff: WlBufferProxy = frame.user_data[1]
        shm_data: mmap.mmap = frame.user_data[2]

        # CAIRO_FORMAT_RGB24 is xrgb
        try:
            with cairo.ImageSurface.create_for_data(
                shm_data,  # type: ignore
                cairo.FORMAT_RGB24,
                self.width,
                self.height,
                self.rowstride,
            ) as surface:
                pixbuf: GdkPixbuf.Pixbuf = Gdk.pixbuf_get_from_surface(
                    surface,
                    0,
                    0,
                    self.width,
                    self.height,
                )
            self.emit("frame-ready", frame.user_data[0], pixbuf)
        except Exception as e:
            logger.error(e)
            shm_data.close()

        buff.destroy()
        frame.destroy()

    def on_buffer_failed(self, frame: HyprlandToplevelExportFrameV1Proxy):
        logger.error(f"[PyWayland] failed to copy buffer for {frame.user_data[0]}")
        print(frame.user_data)
        frame.user_data[1].destroy() if len(frame.user_data) > 1 else None
        frame.destroy()
        self.display.flush()
