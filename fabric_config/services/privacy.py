"""
Privacy: which apps are using the microphone, the camera, or sharing the screen.

All three are PipeWire streams, so this follows the graph with `pw-dump
--monitor` (one long-running process; it prints the whole graph, then each
change as it happens). A capture stream counts while it's running and linked
from a real source: a microphone (not a sink's monitor, which is how cava and
desktop-audio recorders listen), a camera, or a screen-cast node (the portal's,
for browsers, OBS and the like). wf-recorder records through screencopy, not
PipeWire; the bar's recording indicator covers that.
"""

import json
import os
from dataclasses import dataclass
from typing import Literal

from fabric.core.service import Property, Service, Signal
from gi.repository import Gio, GLib
from loguru import logger

UseKind = Literal["mic", "camera", "screen"]
KINDS: tuple[UseKind, ...] = ("mic", "camera", "screen")
RESTART_AFTER_S = 5
# changes come in bursts (a stream and its links, ports and params)
SETTLE_MS = 100
# an unparseable backlog this big means pw-dump's output isn't JSON
MAX_BUFFER = 32 * 1024 * 1024


@dataclass(frozen=True)
class Use:
    kind: UseKind
    app: str
    icon: str | None
    pid: int | None


def _props(obj: dict) -> dict:
    return (obj.get("info") or {}).get("props") or {}


def _is_camera(node: dict) -> bool:
    props = _props(node)
    return (
        props.get("device.api") in ("v4l2", "libcamera")
        or props.get("media.role") == "Camera"
        or str(props.get("node.name", "")).startswith(("v4l2_", "libcamera"))
    )


def _uses(objects: dict[int, dict]) -> list[Use]:
    nodes = {
        i: o for i, o in objects.items() if o.get("type") == "PipeWire:Interface:Node"
    }
    # stream id -> ids of the nodes feeding it
    feeds: dict[int, set[int]] = {}
    for o in objects.values():
        if o.get("type") != "PipeWire:Interface:Link":
            continue
        info = o.get("info") or {}
        out, into = info.get("output-node-id"), info.get("input-node-id")
        if isinstance(out, int) and isinstance(into, int):
            feeds.setdefault(into, set()).add(out)

    uses: list[Use] = []
    for node_id, node in nodes.items():
        props = _props(node)
        media_class = props.get("media.class")
        if media_class not in ("Stream/Input/Audio", "Stream/Input/Video"):
            continue
        if (node.get("info") or {}).get("state") != "running":
            continue
        sources = [nodes[s] for s in feeds.get(node_id, ()) if s in nodes]
        classes = [_props(s).get("media.class", "") for s in sources]
        if media_class == "Stream/Input/Audio":
            if not any(c.startswith("Audio/Source") for c in classes):
                continue  # a sink's monitor, or not connected yet
            kind: UseKind = "mic"
        else:
            video = [
                s for s in sources if _props(s).get("media.class") == "Video/Source"
            ]
            if not video:
                continue
            kind = "camera" if any(_is_camera(s) for s in video) else "screen"
        pid = props.get("application.process.id")
        uses.append(
            Use(
                kind=kind,
                app=str(
                    props.get("application.name")
                    or props.get("application.process.binary")
                    or props.get("node.name")
                    or "Unknown"
                ),
                icon=props.get("application.icon-name")
                or props.get("application.process.binary"),
                pid=pid if isinstance(pid, int) else None,
            )
        )
    # one entry per app and kind (browsers open a stream per tab or track)
    return sorted(set(uses), key=lambda u: (KINDS.index(u.kind), u.app.lower()))


class Privacy(Service):
    @Signal
    def changed(self) -> None: ...

    def __init__(self, **kwargs):
        self._objects: dict[int, dict] = {}
        self._uses: list[Use] = []
        self._buffer = ""
        self._decoder = json.JSONDecoder()
        self._process: Gio.Subprocess | None = None
        self._settle_id: int | None = None
        super().__init__(**kwargs)
        self._start()

    @Property(list, "readable")
    def uses(self) -> list[Use]:
        """What's in use now, by whom; sorted by kind, then app."""
        return self._uses

    def in_use(self, kind: UseKind) -> list[Use]:
        return [u for u in self._uses if u.kind == kind]

    def _start(self):
        self._objects.clear()
        self._buffer = ""
        try:
            self._process = Gio.Subprocess.new(
                ["pw-dump", "--monitor", "--no-colors"],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE,
            )
        except GLib.Error as e:
            logger.error(f"[Privacy] Can't start pw-dump: {e.message}")
            return
        stdout = self._process.get_stdout_pipe()
        if stdout is not None:
            self._read(stdout)

    def _read(self, stream: Gio.InputStream):
        stream.read_bytes_async(65536, GLib.PRIORITY_LOW, None, self._on_read, stream)

    def _on_read(self, stream: Gio.InputStream, result: Gio.AsyncResult, _data):
        try:
            data = stream.read_bytes_finish(result).get_data() or b""
        except GLib.Error as e:
            logger.error(f"[Privacy] Reading pw-dump failed: {e.message}")
            data = b""
        if not data:
            # pw-dump quit (PipeWire restarted?): start over in a bit
            logger.warning("[Privacy] pw-dump exited; restarting")
            self._process = None
            GLib.timeout_add_seconds(RESTART_AFTER_S, lambda: self._start() and False)
            return
        self._buffer += data.decode("utf-8", errors="replace")
        self._parse()
        self._read(stream)

    def _parse(self):
        changed = False
        while True:
            text = self._buffer.lstrip()
            if not text:
                self._buffer = ""
                break
            try:
                batch, end = self._decoder.raw_decode(text)
            except json.JSONDecodeError:
                if len(text) > MAX_BUFFER:
                    logger.error("[Privacy] Can't parse pw-dump's output")
                    text = ""
                self._buffer = text  # wait for the rest
                break
            self._buffer = text[end:]
            for obj in batch if isinstance(batch, list) else ():
                if isinstance(obj, dict) and isinstance(obj.get("id"), int):
                    changed = self._apply(obj) or changed
        if changed and self._settle_id is None:
            self._settle_id = GLib.timeout_add(SETTLE_MS, self._update)

    def _apply(self, obj: dict) -> bool:
        object_id = obj["id"]
        if obj.get("info") is None:
            return self._objects.pop(object_id, None) is not None
        if obj.get("type") is None and object_id in self._objects:
            # a partial update: keep what we know
            merged = dict(self._objects[object_id])
            merged["info"] = {**(merged.get("info") or {}), **obj["info"]}
            obj = merged
        if obj.get("type") not in (
            "PipeWire:Interface:Node",
            "PipeWire:Interface:Link",
        ):
            return False
        self._objects[object_id] = obj
        return True

    def _update(self) -> bool:
        self._settle_id = None
        uses = _uses(self._objects)
        own = os.getpid()
        uses = [u for u in uses if u.pid != own]
        if uses != self._uses:
            self._uses = uses
            self.notify("uses")
            self.changed()
        return False
