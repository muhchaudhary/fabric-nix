import hashlib
import json
import os
import re
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Callable, Literal

import gi
from fabric import Property, Service, Signal
from loguru import logger

from fabric_config.utils.uri import file_uri_to_path

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib  # noqa: E402

# "[[ binary data 82 KiB png 535x440 ]]"
_BINARY_RE = re.compile(
    r"^\[\[ binary data (?P<size>\S+ \S+) (?P<format>\w+)(?: (?P<w>\d+)x(?P<h>\d+))? \]\]$"
)
# cliphist marks previews cut at -preview-width with a trailing ellipsis
_TRUNCATED_SUFFIX = "…"

THUMBNAIL_WIDTH = 720  # ~2x the card width, for HiDPI
THUMBNAIL_HEIGHT = 480
MAX_CONCURRENT_DECODES = 2

SUPPORTED_IMAGE_EXTENSIONS = {
    ext for fmt in GdkPixbuf.Pixbuf.get_formats() for ext in fmt.get_extensions()
}

PINS_DIR = os.path.join(GLib.get_user_data_dir(), "fabric", "clipboard")
PINS_FILE = os.path.join(PINS_DIR, "pins.json")

EntryKind = Literal["text", "image", "html", "file"]


@dataclass(frozen=True)
class ClipEntry:
    """One `cliphist list` row. `preview` is cliphist's (possibly truncated) text."""

    id: str
    preview: str
    kind: EntryKind
    image_format: str | None = None  # for images, e.g. "png"
    size_label: str | None = None  # for images, e.g. "82 KiB"
    dimensions: tuple[int, int] | None = None  # for images

    @property
    def truncated(self) -> bool:
        return self.kind == "text" and self.preview.endswith(_TRUNCATED_SUFFIX)

    @property
    def path(self) -> str | None:
        return self.preview if self.kind == "file" else None


@dataclass
class Pin:
    """A pinned item, stored independently of cliphist so it survives re-copies
    (which give the entry a new id) and cliphist's max-items pruning."""

    key: str
    kind: Literal["text", "image"]
    text: str | None = None  # for text pins
    file: str | None = None  # for image pins, relative to PINS_DIR
    mime: str | None = None  # for image pins
    source_id: str | None = None  # cliphist id it was pinned from, if any


def _parse_entry(cliphist_id: str, preview: str) -> ClipEntry:
    if m := _BINARY_RE.match(preview):
        dims = (int(m["w"]), int(m["h"])) if m["w"] else None
        return ClipEntry(
            cliphist_id,
            preview,
            "image",
            image_format=m["format"],
            size_label=m["size"],
            dimensions=dims,
        )
    if preview.startswith("<meta") and "<img" in preview:
        # an image copied from a browser, stored as HTML (the image itself is
        # usually also stored as a separate binary entry)
        return ClipEntry(cliphist_id, preview, "html")
    candidate = preview.strip()
    if candidate.startswith("file://"):
        candidate = file_uri_to_path(candidate)
    if (
        candidate.startswith("/")
        and "\n" not in candidate
        and len(candidate) < 1024
        and not preview.endswith(_TRUNCATED_SUFFIX)
        and os.path.exists(candidate)
    ):
        return ClipEntry(cliphist_id, candidate, "file")
    return ClipEntry(cliphist_id, preview, "text")


def _cliphist_db_path() -> str:
    return os.environ.get("CLIPHIST_DB_PATH") or os.path.join(
        GLib.get_user_cache_dir(), "cliphist", "db"
    )


def _run(
    argv: list[str],
    callback: Callable[[bool, bytes], None],
    stdin: bytes | None = None,
    capture_stdout: bool = True,
):
    """
    Run argv; callback(success, stdout_bytes) on exit. stdin is closed after
    writing. Use capture_stdout=False for commands that leave a background
    child running (wl-copy): the child would keep the pipe open and the
    callback would never fire.
    """
    flags = Gio.SubprocessFlags.STDERR_SILENCE | (
        Gio.SubprocessFlags.STDOUT_PIPE
        if capture_stdout
        else Gio.SubprocessFlags.STDOUT_SILENCE
    )
    if stdin is not None:
        flags |= Gio.SubprocessFlags.STDIN_PIPE
    try:
        proc = Gio.Subprocess.new(argv, flags)
    except GLib.Error as e:
        logger.error(f"[CLIPBOARD] Failed to start {argv[0]}: {e.message}")
        callback(False, b"")
        return

    def on_done(p: Gio.Subprocess, result: Gio.AsyncResult):
        try:
            _, out, _ = p.communicate_finish(result)
        except GLib.Error as e:
            logger.error(f"[CLIPBOARD] {argv[0]} failed: {e.message}")
            callback(False, b"")
            return
        callback(p.get_successful(), out.get_data() if out else b"")

    proc.communicate_async(
        GLib.Bytes.new(stdin) if stdin is not None else None, None, on_done
    )


class ClipboardHistory(Service):
    @Signal
    def clipboard_deleted(self, cliphist_id: str) -> str: ...

    @Signal
    def clipboard_copied(self, cliphist_id: str) -> str: ...

    @Signal
    def thumbnail_ready(self, key: str) -> str: ...

    @Signal
    def pins_changed(self) -> None: ...

    def __init__(self, **kwargs):
        self._entries: list[ClipEntry] = []
        self._by_id: dict[str, ClipEntry] = {}
        self._thumbnails: dict[str, GdkPixbuf.Pixbuf] = {}
        self._decode_queue: deque[str] = deque()
        self._queued: set[str] = set()
        self._decoding = 0
        # full-text hashes for truncated entries whose previews collide, so
        # exact duplicates can be hidden without decoding every entry
        self._full_hashes: dict[str, str] = {}
        self._hashing: set[str] = set()
        self._last_listing = ""
        self._pins: list[Pin] = self._load_pins()
        super().__init__(**kwargs)

        # Watch cliphist's database instead of running `wl-paste --watch`: no
        # extra process (which used to outlive the bar), and it also catches
        # deletions made elsewhere. Writes come in bursts, so debounce.
        self._refresh_timeout_id: int | None = None
        self._db_monitor: Gio.FileMonitor | None = None
        try:
            self._db_monitor = Gio.File.new_for_path(_cliphist_db_path()).monitor_file(
                Gio.FileMonitorFlags.NONE, None
            )
            self._db_monitor.connect("changed", lambda *_: self._schedule_refresh())
        except GLib.Error as e:
            logger.error(f"[CLIPBOARD] Can't watch cliphist db: {e.message}")
        self.refresh()

    # ---- history ---------------------------------------------------------

    @Property(list, "readable")
    def entries(self) -> list[ClipEntry]:
        """Newest first, with exact duplicate text entries removed."""
        return self._entries

    @Property(dict, "readable")
    def clipboard_history(self) -> dict:
        # kept for compatibility: id -> preview
        return {e.id: e.preview for e in self._entries}

    def get_entry(self, cliphist_id: str) -> ClipEntry | None:
        return self._by_id.get(cliphist_id)

    def _schedule_refresh(self):
        if self._refresh_timeout_id is not None:
            GLib.source_remove(self._refresh_timeout_id)
        self._refresh_timeout_id = GLib.timeout_add(150, self._do_scheduled_refresh)

    def _do_scheduled_refresh(self):
        self._refresh_timeout_id = None
        self.refresh()
        return False

    def refresh(self, on_done: Callable[[], None] | None = None):
        def on_list(ok: bool, out: bytes):
            if ok:
                self._set_entries(out.decode("utf-8", errors="replace"))
            else:
                logger.error("[CLIPBOARD] `cliphist list` failed")
            if on_done:
                on_done()

        _run(["cliphist", "list"], on_list)

    def _set_entries(self, listing: str):
        self._last_listing = listing
        parsed: list[ClipEntry] = []
        for line in listing.splitlines():
            cliphist_id, sep, preview = line.partition("\t")
            if not sep:
                continue
            entry = self._by_id.get(cliphist_id)
            if entry is None or entry.preview != preview:
                entry = _parse_entry(cliphist_id, preview)
            parsed.append(entry)

        # cliphist only de-duplicates against its most recent entries, so hide
        # older exact copies. Complete previews compare directly; truncated ones
        # only match once their full texts are known to be equal.
        preview_counts: dict[str, int] = {}
        for e in parsed:
            if e.truncated:
                preview_counts[e.preview] = preview_counts.get(e.preview, 0) + 1
        to_hash = [
            e.id
            for e in parsed
            if e.truncated
            and preview_counts[e.preview] > 1
            and e.id not in self._full_hashes
        ]

        entries: list[ClipEntry] = []
        seen: set[str] = set()
        for e in parsed:
            if e.kind == "text" and not e.truncated:
                key = "text:" + e.preview
            elif e.truncated and e.id in self._full_hashes:
                key = "hash:" + self._full_hashes[e.id]
            else:
                key = "id:" + e.id
            if key in seen:
                continue
            seen.add(key)
            entries.append(e)

        self._entries = entries
        self._by_id = {e.id: e for e in entries}
        # free thumbnails of entries that are gone (pin thumbnails use "pin:" keys)
        for key in [k for k in self._thumbnails if not k.startswith("pin:")]:
            if key not in self._by_id:
                del self._thumbnails[key]
        listed = {e.id for e in parsed}
        for key in [k for k in self._full_hashes if k not in listed]:
            del self._full_hashes[key]
        self.notify("entries")
        self.notify("clipboard-history")
        self._hash_entries(to_hash)

    def _hash_entries(self, ids: list[str]):
        pending = [i for i in ids if i not in self._hashing]
        if not pending:
            return
        self._hashing.update(pending)
        remaining = len(pending)

        def on_decoded(cliphist_id: str, ok: bool, data: bytes):
            nonlocal remaining
            self._hashing.discard(cliphist_id)
            # record failures as unique values so they aren't retried in a loop
            self._full_hashes[cliphist_id] = (
                hashlib.sha1(data).hexdigest() if ok else f"unhashable:{cliphist_id}"
            )
            remaining -= 1
            if remaining == 0:
                # re-evaluate duplicates now that the full texts are known
                self._set_entries(self._last_listing)

        for cliphist_id in pending:
            _run(
                ["cliphist", "decode", cliphist_id],
                lambda ok, data, i=cliphist_id: on_decoded(i, ok, data),
            )

    # ---- thumbnails ------------------------------------------------------

    def get_thumbnail(self, key: str) -> GdkPixbuf.Pixbuf | None:
        return self._thumbnails.get(key)

    def request_thumbnail(self, key: str):
        """
        Load a downscaled preview for an image/file entry id or a "pin:<key>".
        Emits thumbnail-ready(key) when available. Decodes run asynchronously,
        at most MAX_CONCURRENT_DECODES at a time.
        """
        if key in self._thumbnails:
            self.thumbnail_ready(key)
            return
        if key in self._queued:
            return
        self._queued.add(key)
        self._decode_queue.append(key)
        self._pump_decode_queue()

    def _pump_decode_queue(self):
        while self._decoding < MAX_CONCURRENT_DECODES and self._decode_queue:
            key = self._decode_queue.popleft()
            self._decoding += 1
            self._start_decode(key)

    def _finish_decode(self, key: str, pixbuf: GdkPixbuf.Pixbuf | None):
        self._decoding -= 1
        self._queued.discard(key)
        if pixbuf is not None:
            self._thumbnails[key] = pixbuf
            self.thumbnail_ready(key)
        self._pump_decode_queue()

    def _load_scaled(self, stream: Gio.InputStream, key: str):
        def on_pixbuf(_src, result: Gio.AsyncResult):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_stream_finish(result)
            except GLib.Error as e:
                logger.debug(f"[CLIPBOARD] No thumbnail for {key}: {e.message}")
                pixbuf = None
            self._finish_decode(key, pixbuf)

        GdkPixbuf.Pixbuf.new_from_stream_at_scale_async(
            stream, THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT, True, None, on_pixbuf
        )

    def _load_file(self, path: str, key: str):
        def on_read(file: Gio.File, result: Gio.AsyncResult):
            try:
                self._load_scaled(file.read_finish(result), key)
            except GLib.Error:
                self._finish_decode(key, None)

        Gio.File.new_for_path(path).read_async(GLib.PRIORITY_LOW, None, on_read)

    def _start_decode(self, key: str):
        if key.startswith("pin:"):
            pin = self._pin_by_key(key[4:])
            if pin is None or pin.file is None:
                self._finish_decode(key, None)
                return
            self._load_file(os.path.join(PINS_DIR, pin.file), key)
            return

        entry = self._by_id.get(key)
        if entry is None:
            self._finish_decode(key, None)
        elif entry.kind == "image":
            try:
                proc = Gio.Subprocess.new(
                    ["cliphist", "decode", entry.id],
                    Gio.SubprocessFlags.STDOUT_PIPE
                    | Gio.SubprocessFlags.STDERR_SILENCE,
                )
            except GLib.Error:
                self._finish_decode(key, None)
                return
            self._load_scaled(proc.get_stdout_pipe(), key)
        elif entry.kind == "file" and entry.path:
            ext = os.path.splitext(entry.path)[1].lstrip(".").lower()
            if ext in SUPPORTED_IMAGE_EXTENSIONS and os.path.isfile(entry.path):
                self._load_file(entry.path, key)
            else:
                self._finish_decode(key, None)
        else:
            # text and html entries never need decoding; html images are not
            # fetched, so copying never triggers network requests
            self._finish_decode(key, None)

    # ---- actions ---------------------------------------------------------

    def copy(self, cliphist_id: str, on_done: Callable[[bool], None] | None = None):
        entry = self._by_id.get(cliphist_id)
        if entry is None:
            if on_done:
                on_done(False)
            return

        def on_decoded(ok: bool, data: bytes):
            if not ok:
                logger.error(f"[CLIPBOARD] Failed to decode {cliphist_id}")
                if on_done:
                    on_done(False)
                return
            mime = None
            if entry.kind == "html":
                mime = "text/html"  # paste as the image/markup, not as source text
            elif entry.kind == "image" and entry.image_format:
                mime = f"image/{entry.image_format}"
            self._wl_copy(
                data, mime, lambda ok: self._after_copy(cliphist_id, ok, on_done)
            )

        _run(["cliphist", "decode", cliphist_id], on_decoded)

    def _after_copy(self, cliphist_id: str, ok: bool, on_done):
        if ok:
            self.clipboard_copied(cliphist_id)
        if on_done:
            on_done(ok)

    def _wl_copy(self, data: bytes, mime: str | None, on_done: Callable[[bool], None]):
        argv = ["wl-copy"] + (["--type", mime] if mime else [])
        _run(argv, lambda ok, _out: on_done(ok), stdin=data, capture_stdout=False)

    def delete(
        self, cliphist_ids: list[str], on_done: Callable[[], None] | None = None
    ):
        """Delete entries with a single `cliphist delete` (reads ids until EOF)."""
        lines = "".join(
            f"{i}\t{self._by_id[i].preview}\n" for i in cliphist_ids if i in self._by_id
        )
        if not lines:
            return

        def on_deleted(ok: bool, _out: bytes):
            if not ok:
                logger.error(f"[CLIPBOARD] cliphist delete failed for {cliphist_ids}")
            for i in cliphist_ids:
                self.clipboard_deleted(i)
            # the db monitor also notices, but refresh now so the UI is immediate
            self.refresh(on_done)

        _run(["cliphist", "delete"], on_deleted, stdin=lines.encode())

    def clear(self, on_done: Callable[[], None] | None = None):
        """Delete all history. Pins are stored separately and are kept."""
        self.delete([e.id for e in self._entries], on_done)

    # ---- pins ------------------------------------------------------------

    @Property(list, "readable")
    def pins(self) -> list[Pin]:
        return self._pins

    def _pin_by_key(self, key: str) -> Pin | None:
        return next((p for p in self._pins if p.key == key), None)

    def pin_for_entry(self, cliphist_id: str) -> Pin | None:
        entry = self._by_id.get(cliphist_id)
        for pin in self._pins:
            if pin.source_id == cliphist_id:
                return pin
            if (
                entry is not None
                and entry.kind == "text"
                and not entry.truncated
                and pin.kind == "text"
                and pin.text == entry.preview
            ):
                return pin
        return None

    def pin(self, cliphist_id: str):
        entry = self._by_id.get(cliphist_id)
        if entry is None or self.pin_for_entry(cliphist_id):
            return

        def on_decoded(ok: bool, data: bytes):
            if not ok:
                logger.error(f"[CLIPBOARD] Failed to pin {cliphist_id}")
                return
            key = uuid.uuid4().hex
            if entry.kind == "image":
                ext = entry.image_format or "png"
                file = f"{key}.{ext}"
                os.makedirs(PINS_DIR, exist_ok=True)
                with open(os.path.join(PINS_DIR, file), "wb") as f:
                    f.write(data)
                pin = Pin(
                    key, "image", file=file, mime=f"image/{ext}", source_id=cliphist_id
                )
                # reuse the already-decoded thumbnail if there is one
                if cliphist_id in self._thumbnails:
                    self._thumbnails[f"pin:{key}"] = self._thumbnails[cliphist_id]
            else:
                pin = Pin(
                    key,
                    "text",
                    text=data.decode("utf-8", errors="replace"),
                    source_id=cliphist_id,
                )
            self._pins.insert(0, pin)
            self._save_pins()
            self.pins_changed()

        _run(["cliphist", "decode", cliphist_id], on_decoded)

    def unpin(self, key: str):
        pin = self._pin_by_key(key)
        if pin is None:
            return
        self._pins.remove(pin)
        if pin.file:
            try:
                os.remove(os.path.join(PINS_DIR, pin.file))
            except OSError:
                pass
        self._thumbnails.pop(f"pin:{key}", None)
        self._save_pins()
        self.pins_changed()

    def copy_pin(self, key: str, on_done: Callable[[bool], None] | None = None):
        pin = self._pin_by_key(key)
        if pin is None:
            if on_done:
                on_done(False)
            return
        if pin.kind == "image" and pin.file:
            try:
                with open(os.path.join(PINS_DIR, pin.file), "rb") as f:
                    data = f.read()
            except OSError as e:
                logger.error(f"[CLIPBOARD] Pinned image missing: {e}")
                if on_done:
                    on_done(False)
                return
            self._wl_copy(data, pin.mime, on_done or (lambda _ok: None))
        else:
            self._wl_copy(
                (pin.text or "").encode(), None, on_done or (lambda _ok: None)
            )

    def _load_pins(self) -> list[Pin]:
        try:
            with open(PINS_FILE) as f:
                return [Pin(**p) for p in json.load(f)]
        except FileNotFoundError:
            return []
        except (OSError, ValueError, TypeError) as e:
            logger.error(f"[CLIPBOARD] Couldn't read pins: {e}")
            return []

    def _save_pins(self):
        os.makedirs(PINS_DIR, exist_ok=True)
        tmp = PINS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump([p.__dict__ for p in self._pins], f)
        os.replace(tmp, PINS_FILE)  # atomic, so a crash can't corrupt pins
