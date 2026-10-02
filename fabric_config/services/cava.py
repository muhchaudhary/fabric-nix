"""
cava (console audio visualizer) as a shared source of audio levels.

Several parts of the bar draw levels (the desktop visualizer, the music
seek bars); each says whether it currently wants them with
`set_wanted(owner, bool)`, and cava runs only while at least one does.
"""

import os

from fabric.core.service import Service, Signal
from gi.repository import Gio, GLib
from loguru import logger

CAVA_BARS = 64
CAVA_CONFIG = os.path.join(GLib.get_user_cache_dir(), "fabric", "cava.conf")


class Cava(Service):
    """
    Runs cava while someone wants bars, reading its raw ASCII output: one
    line per frame, values 0-1000 separated by ';'.
    """

    @Signal
    def frame(self) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bars: list[float] = [0.0] * CAVA_BARS
        self.available = GLib.find_program_in_path("cava") is not None
        self._process: Gio.Subprocess | None = None
        self._stream: Gio.DataInputStream | None = None
        self._cancellable: Gio.Cancellable | None = None
        self._wanted_by: set[str] = set()

    @property
    def running(self) -> bool:
        return self._process is not None

    def set_wanted(self, owner: str, wanted: bool):
        """Ask for levels (or stop asking); cava runs while anyone asks."""
        if wanted:
            self._wanted_by.add(owner)
        else:
            self._wanted_by.discard(owner)
        if self._wanted_by and not self.running:
            self.start()
        elif not self._wanted_by and self.running:
            self.stop()

    def _write_config(self):
        os.makedirs(os.path.dirname(CAVA_CONFIG), exist_ok=True)
        with open(CAVA_CONFIG, "w") as f:
            f.write(
                f"""[general]
bars = {CAVA_BARS}
framerate = 30
autosens = 1

[input]
method = pulse
source = auto

[output]
method = raw
raw_target = /dev/stdout
data_format = ascii
ascii_max_range = 1000
bar_delimiter = 59
frame_delimiter = 10

[smoothing]
noise_reduction = 77
"""
            )

    def start(self):
        if self.running or not self.available:
            return
        try:
            self._write_config()
            self._process = Gio.Subprocess.new(
                ["cava", "-p", CAVA_CONFIG],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE,
            )
        except (GLib.Error, OSError) as e:
            logger.warning(f"[Desktop] Couldn't start cava: {e}")
            self.available = False
            self._process = None
            return
        pipe = self._process.get_stdout_pipe()
        if pipe is None:
            self.stop()
            return
        self._stream = Gio.DataInputStream.new(pipe)
        self._cancellable = Gio.Cancellable()
        self._read_next()

    def stop(self):
        if self._cancellable is not None:
            self._cancellable.cancel()
        if self._process is not None:
            self._process.force_exit()
        self._process = None
        self._stream = None
        self._cancellable = None
        self.bars = [0.0] * CAVA_BARS
        self.frame()

    def _read_next(self):
        if self._stream is None:
            return
        self._stream.read_line_async(
            GLib.PRIORITY_DEFAULT, self._cancellable, self._on_line
        )

    def _on_line(self, stream: Gio.DataInputStream, result: Gio.AsyncResult):
        try:
            line, _length = stream.read_line_finish_utf8(result)
        except GLib.Error:
            return  # cancelled or the process went away
        if line is None:
            self.stop()
            return
        values = [v for v in line.split(";") if v]
        if len(values) >= CAVA_BARS:
            try:
                self.bars = [int(v) / 1000 for v in values[:CAVA_BARS]]
            except ValueError:
                pass
            self.frame()
        self._read_next()
