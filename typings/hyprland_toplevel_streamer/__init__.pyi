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
