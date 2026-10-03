import math
from collections.abc import Callable, Hashable

import cairo
from gi.repository import GLib
import hyprland_toplevel_streamer as streamer
from loguru import logger

# last frames kept for windows nobody watches, so a preview shows at once
CACHE_SIZE = 48


def cover_size(
    window_size: tuple[int, int] | list[int], width: int, height: int
) -> tuple[int, int]:
    """
    The frame size to ask for so a window covers a width x height preview.

    Frames keep the window's aspect ratio and fit inside the requested box,
    so ask for the window scaled until it covers the preview; the preview
    then crops the overflow instead of enlarging a frame that's too small.
    """
    window_width, window_height = (max(1, v) for v in window_size)
    factor = max(width / window_width, height / window_height)
    return (
        max(1, math.ceil(window_width * factor)),
        max(1, math.ceil(window_height * factor)),
    )


class _Subscription:
    __slots__ = ("width", "height", "fps", "on_frame")

    def __init__(
        self,
        width: int,
        height: int,
        fps: float,
        on_frame: Callable[[cairo.ImageSurface], None],
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.on_frame = on_frame


class WindowPreviews:
    """
    Live window previews (`config.window_previews`).

    Wraps one `PreviewHub` from toplevel-streamer-rs: a Rust thread that
    captures each watched window when it redraws (capped at a frame rate),
    scales it down and hands back premultiplied BGRA, which is cairo's ARGB32,
    so frames paint without conversion. Its eventfd is watched by the GLib
    loop, so nothing polls and no Python runs per frame until one is ready.

    Several owners can watch the same window: it is captured at the largest
    size and frame rate any of them asks for. Owners unsubscribe when their
    preview is hidden; a window nobody watches isn't captured at all.
    """

    def __init__(self):
        self._hub: streamer.PreviewHub | None = None
        self._source_id: int | None = None
        # all keyed by window handle (the address as an int)
        self._subs: dict[int, dict[Hashable, _Subscription]] = {}
        # (width, height, fps) the hub is watching each window with
        self._watching: dict[int, tuple[int, int, float]] = {}
        self._last: dict[int, cairo.ImageSurface] = {}
        self._warned = False

    def subscribe(
        self,
        owner: Hashable,
        address: str,
        width: int,
        height: int,
        on_frame: Callable[[cairo.ImageSurface], None],
        fps: float = 30,
    ) -> cairo.ImageSurface | None:
        """
        Call `on_frame(surface)` with live frames of the window at `address`
        (a Hyprland "0x..." address). Frames fit inside width x height device
        pixels, keeping the window's aspect ratio. Returns the window's last
        frame, if any, to show until the first live one arrives.
        """
        if self._ensure_hub() is None:
            return None
        handle = int(address, 16)
        self._subs.setdefault(handle, {})[owner] = _Subscription(
            max(1, width), max(1, height), fps, on_frame
        )
        self._sync(handle)
        return self._last.get(handle)

    def unsubscribe(self, owner: Hashable, address: str | None = None):
        """Stop sending `owner` frames of `address`, or of every window."""
        handles = [int(address, 16)] if address is not None else list(self._subs)
        for handle in handles:
            subs = self._subs.get(handle)
            if subs is not None and subs.pop(owner, None) is not None:
                if not subs:
                    del self._subs[handle]
                self._sync(handle)

    def last_frame(self, address: str) -> cairo.ImageSurface | None:
        return self._last.get(int(address, 16))

    def _ensure_hub(self) -> streamer.PreviewHub | None:
        if self._hub is not None and self._hub.error() is None:
            return self._hub
        if self._hub is not None:
            logger.warning(f"[Previews] restarting capture: {self._hub.error()}")
            self._stop_hub()
        # toplevel-streamer-rs releases before PreviewHub still import fine
        if not hasattr(streamer, "PreviewHub"):
            if not self._warned:
                self._warned = True
                logger.error(
                    "[Previews] hyprland_toplevel_streamer has no PreviewHub; "
                    "update the toplevel-streamer-rs flake input"
                )
            return None
        try:
            hub = streamer.PreviewHub()
        except Exception as e:
            logger.error(f"[Previews] live previews unavailable: {e}")
            return None
        self._hub = hub
        self._source_id = GLib.io_add_watch(
            GLib.IOChannel.unix_new(hub.fileno()),
            GLib.PRIORITY_DEFAULT,
            GLib.IOCondition.IN,
            self._on_ready,
        )
        return hub

    def _stop_hub(self):
        if self._source_id is not None:
            GLib.source_remove(self._source_id)
            self._source_id = None
        if self._hub is not None:
            self._hub.close()
            self._hub = None
        self._watching.clear()

    def _sync(self, handle: int):
        """Point the hub at the biggest size and rate any subscriber wants."""
        hub = self._hub
        if hub is None:
            return
        subs = self._subs.get(handle)
        try:
            if not subs:
                if self._watching.pop(handle, None) is not None:
                    hub.unwatch(handle)
                return
            wanted = (
                max(s.width for s in subs.values()),
                max(s.height for s in subs.values()),
                max(s.fps for s in subs.values()),
            )
            if self._watching.get(handle) != wanted:
                hub.watch(handle, wanted[0], wanted[1], fps=wanted[2])
                self._watching[handle] = wanted
        except Exception as e:
            logger.error(f"[Previews] couldn't watch 0x{handle:x}: {e}")

    def _on_ready(self, *_) -> bool:
        hub = self._hub
        if hub is None:
            return False
        for frame in hub.take_frames():
            handle = frame.window_handle
            surface = cairo.ImageSurface.create_for_data(
                bytearray(frame.data),
                cairo.FORMAT_ARGB32,
                frame.width,
                frame.height,
                frame.stride,
            )
            # re-insert so the dict stays ordered oldest first
            self._last.pop(handle, None)
            self._last[handle] = surface
            for sub in list(self._subs.get(handle, {}).values()):
                sub.on_frame(surface)
        excess = len(self._last) - CACHE_SIZE
        if excess > 0:
            unused = [h for h in self._last if h not in self._subs]
            for handle in unused[:excess]:
                del self._last[handle]

        for handle in hub.take_failures():
            # usually a window that just closed; it is retried while watched
            logger.debug(f"[Previews] capturing 0x{handle:x} failed")

        if (error := hub.error()) is not None:
            logger.error(f"[Previews] capture thread stopped: {error}")
            self._source_id = None
            self._hub = None
            self._watching.clear()
            return False
        return True
