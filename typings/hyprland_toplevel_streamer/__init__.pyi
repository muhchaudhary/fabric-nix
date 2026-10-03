# Stubs for the toplevel-streamer-rs pyo3 extension, which ships no .pyi
from collections.abc import Iterator
from typing import Literal, final

@final
class Frame:
    """width * height * 4 bytes, rowstride == width * 4, already y-corrected."""

    @property
    def data(self) -> bytes: ...
    @property
    def width(self) -> int: ...
    @property
    def height(self) -> int: ...
    @property
    def rowstride(self) -> int: ...
    @property
    def pixel_format(self) -> Literal["RGBA", "BGRA"]: ...

@final
class PyFrameInfo:
    @property
    def format(self) -> str: ...
    @property
    def width(self) -> int: ...
    @property
    def height(self) -> int: ...
    @property
    def stride(self) -> int: ...

@final
class WindowStream:
    def __iter__(self) -> Iterator[Frame]: ...
    def __next__(self) -> Frame: ...
    def next_frame(self) -> Frame: ...
    def close(self) -> None: ...

@final
class HyprlandFrameCapture:
    def __init__(self) -> None: ...
    def capture(
        self,
        window_handle: int,
        overlay_cursor: bool = True,
        ignore_damage: bool = True,
        rgba: bool = True,
        max_size: int = 0,
    ) -> Frame: ...
    def capture_frame(
        self,
        window_handle: int,
        overlay_cursor: bool = True,
        ignore_damage: bool = True,
    ) -> tuple[bytes, PyFrameInfo]: ...
    def release(self, window_handle: int) -> None: ...
    def stream(
        self,
        window_handle: int,
        overlay_cursor: bool = True,
        ignore_damage: bool = False,
        rgba: bool = True,
        max_size: int = 0,
    ) -> WindowStream: ...

@final
class PreviewFrame:
    """A downscaled live frame of one window.

    ``data`` is premultiplied BGRA with ``stride == width * 4``: cairo's
    ``FORMAT_ARGB32`` on little-endian machines.
    """

    @property
    def window_handle(self) -> int: ...
    @property
    def width(self) -> int: ...
    @property
    def height(self) -> int: ...
    @property
    def stride(self) -> int: ...
    @property
    def data(self) -> bytes: ...

@final
class PreviewHub:
    """Live previews of many windows, captured on a background Rust thread.

    Each watched window is captured when it redraws, at most ``fps`` times a
    second. Wait for ``fileno()`` to become readable, then ``take_frames()``.
    Thread-safe.
    """

    def __init__(self) -> None: ...
    def watch(
        self,
        window_handle: int,
        max_width: int,
        max_height: int,
        fps: float = 30.0,
        overlay_cursor: bool = False,
    ) -> None:
        """Start or update a preview; frames fit inside max_width x max_height
        (device pixels), keeping the aspect ratio and never enlarged."""
    def unwatch(self, window_handle: int) -> None: ...
    def fileno(self) -> int:
        """An eventfd that becomes readable when frames or failures wait."""
    def take_frames(self) -> list[PreviewFrame]:
        """The newest frame of each window since the last call."""
    def take_failures(self) -> list[int]:
        """Windows whose capture started failing; they are retried."""
    def error(self) -> str | None:
        """Why the background thread stopped, or None while it runs."""
    def close(self) -> None: ...
