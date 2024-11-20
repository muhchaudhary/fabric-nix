import mimetypes
import os
import re
from typing import Callable

import gi
from fabric import Fabricator, Property, Service, Signal

from loguru import logger

gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Rsvg", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib, Rsvg


SUPPORTED_FORMATS = [fmt.name for fmt in GdkPixbuf.Pixbuf.get_formats()]


def get_file_pixbuf_async(file_path: str, callback: Callable):
    def on_file_read(stream: Gio.InputStream, task: Gio.Task):
        try:
            input_stream = stream.read_finish(task)
            GdkPixbuf.Pixbuf.new_from_stream_async(input_stream, None, callback)
            input_stream.close_async(GLib.PRIORITY_DEFAULT, None, None)
        except Exception as _:
            logger.error(
                f"[CLIPBOARD] Failed to create input stream for file: {file_path}"
            )

    file: Gio.File = Gio.File.new_for_path(file_path)
    file.read_async(GLib.PRIORITY_DEFAULT, None, on_file_read)


# Don't need this, sending a gif to GdkPixbuf will return a static image anyways
def get_file_pixbuf_animation_async(
    file_path: str, callback: Callable, user_data: any = None
):
    def on_file_read(stream: Gio.InputStream, task: Gio.Task, user_data):
        try:
            input_stream = stream.read_finish(task)
            GdkPixbuf.PixbufAnimation.new_from_stream_async(
                input_stream, None, callback, user_data
            )
            input_stream.close_async(GLib.PRIORITY_DEFAULT, None, None)
        except Exception as e:
            logger.error(
                f"[CLIPBOARD] Failed to read pixbuf animation from {file_path}"
            )

    file: Gio.File = Gio.File.new_for_path(file_path)
    file.read_async(GLib.PRIORITY_DEFAULT, None, on_file_read, user_data)


class ClipboardHistory(Service):
    @Signal
    def clipboard_deleted(self, cliphist_id: str) -> str: ...
    @Signal
    def clipboard_copied(self, cliphist_id: str) -> str: ...
    @Signal
    def clipboard_data_ready(self, cliphist_id: str) -> str: ...

    def __init__(self, length_cutoff: int = 5000):
        self._length_cutoff = length_cutoff
        self._clipboard_history = {}
        self._decoded_clipboard_history = {}
        super().__init__()
        self.wl_paste_watcher = Fabricator(
            poll_from="wl-paste --watch bash -c ' sleep 0.5 && echo '",
            stream=True,
            interval=-1,
        )
        self.wl_paste_watcher.connect("changed", lambda *_: self.cliphist_list())

    def cliphist_list(self):
        def callback(proc: Gio.Subprocess, task: Gio.Task):
            try:
                _, stdout, stderr = proc.communicate_utf8_finish(task)
                self._clipboard_history = {
                    key: value[7:] if value.startswith("file://") else value
                    for x in stdout.split("\n")[:-1]
                    for key, value in [x.split("\t", 1)]
                }
                print(self._clipboard_history)
                self.notify("clipboard-history")
            except Exception as _:
                logger.error("[CLIPBOARD] Failed to read from `cliphist list`")

        process: Gio.Subprocess = Gio.Subprocess.new(
            ["cliphist", "list"],
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
        )  # type: ignore
        process.communicate_utf8_async(None, None, callback)

    def cliphist_decode(self, cliphist_id: str, callback: Callable):
        process = Gio.Subprocess.new(
            ["cliphist", "decode", str(cliphist_id)],
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
        )
        process.communicate_async(None, None, callback)

    def cliphist_copy(self, cliphist_id: str):
        def wl_wait_callback(proc: Gio.Subprocess, task: Gio.Task):
            try:
                x = proc.wait_finish(task)
                print(x)
            except Exception as e:
                logger.error(
                    f"[CLIPBOARD] Failed to copy for id: {cliphist_id} when sending file"
                )

        def wl_copy_callback(proc: Gio.Subprocess, task: Gio.Task):
            try:
                proc.communicate_finish(task)
                self.emit("clipboard-copied", cliphist_id)
            except Exception as _:
                logger.error(
                    f"[CLIPBOARD] Failed to copy for id: {cliphist_id} when sending command"
                )

        def cliphist_decode_callback(proc: Gio.Subprocess, task: Gio.Task):
            try:
                _, stdout, stderr = proc.communicate_finish(task)
                decoded_str: str = stdout.get_data().decode("utf8")
                file_uri = (
                    f"file://{decoded_str}"
                    if not decoded_str.startswith("file://")
                    else decoded_str
                )
                if os.path.exists(file_uri[7:]):
                    proc = Gio.Subprocess.new(
                        [
                            "bash",
                            "-c",
                            f"echo -n '{file_uri}' | wl-copy --type text/uri-list",
                            # f" wl-copy < { stdout.get_data().decode('utf8') }",
                        ],
                        Gio.SubprocessFlags.STDIN_PIPE
                        | Gio.SubprocessFlags.STDERR_PIPE,
                    )
                    print(
                        [
                            "bash",
                            "-c",
                            f"echo -n file://{stdout.get_data().decode('utf8')} | wl-copy --type text/uri-list",
                            # f" wl-copy < { stdout.get_data().decode('utf8') }",
                        ]
                    )
                    proc.wait_async(None, wl_wait_callback)
                else:
                    process.communicate_async(stdout, None, wl_copy_callback)

            except Exception as _:
                print(_)
                logger.error(
                    f"[CLIPBOARD] Failed to copy item with cliphist id: {cliphist_id} after decode"
                )

        process: Gio.Subprocess = Gio.Subprocess.new(
            ["wl-copy"],
            Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
        )  # type: ignore
        # in_pipe: Gio.OutputStream = process.get_stdin_pipe()
        self.cliphist_decode(cliphist_id, cliphist_decode_callback)

    def cliphist_delete(self, cliphist_id: str):
        self.cliphist_id = cliphist_id

        process: Gio.Subprocess = Gio.Subprocess.new(
            ["cliphist", "delete"],
            Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
        )  # type: ignore

        in_pipe: Gio.OutputStream = process.get_stdin_pipe()
        try:
            out_stream: Gio.DataOutputStream = Gio.DataOutputStream.new(in_pipe)
            out_stream.put_string(
                f"{cliphist_id}\t{self._clipboard_history[cliphist_id]}\n", None
            )
            self.emit("clipboard-deleted", self.cliphist_id)
        except Exception as _:
            logger.error(
                f"[CLIPBOARD] Failed to delete item with cliphist id: {cliphist_id}"
            )

    def parse_data_svg(self, cliphist_id: str):
        def callback(proc: Gio.Subprocess, task: Gio.Task):
            try:
                _, stdout, stderr = proc.communicate_finish(task)
                self._decoded_clipboard_history[cliphist_id] = (
                    Rsvg.Handle.new_from_data(stdout.get_data()).get_pixbuf()
                )

                # We can use GdkPixbuf.PixbufLoader as well but I like Rsvg
                #   no real benifit (that I can think of) to using a PixbbufLoader
                # loader = GdkPixbuf.PixbufLoader()
                # loader.write(stdout.get_data())
                # loader.close()
                # self._decoded_clipboard_history[cliphist_id] = loader.get_pixbuf()
                self.emit("clipboard-data-ready", cliphist_id)
            except Exception as e:
                logger.error(
                    f"[CLIPBOARD] Failed read svg data with cliphist id: {cliphist_id}",
                    e,
                )

        self.cliphist_decode(cliphist_id, callback)

    def parse_data_binary(self, cliphist_id: str):
        preview = self._clipboard_history[cliphist_id]
        info = preview.split()
        # _size = info[3:5]
        data_type = info[5]
        # image_dimensions = tuple(map(int, info[6].split("x")))

        def callback(pixbuf_loader: GdkPixbuf.Pixbuf, task: Gio.Task):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_stream_finish(task)
                self._decoded_clipboard_history[cliphist_id] = pixbuf
                self.emit("clipboard-data-ready", cliphist_id)

            except Exception as _:
                logger.error(
                    f"[CLIPBOARD] Failed to read pixbuf data from cliphist id: {cliphist_id}"
                )

        process: Gio.Subprocess = Gio.Subprocess.new(
            ["cliphist", "decode", str(cliphist_id)],
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
        )  # type: ignore

        if data_type in SUPPORTED_FORMATS:
            GdkPixbuf.Pixbuf.new_from_stream_async(
                process.get_stdout_pipe(), None, callback
            )

    def parse_html_tag(self, cliphist_id: str):
        def on_pixbuf_ready(loader, result):
            try:
                self._decoded_clipboard_history[cliphist_id] = (
                    GdkPixbuf.Pixbuf.new_from_stream_finish(result)
                )
                self.emit("clipboard-data-ready", cliphist_id)
            except Exception as e:
                print(e)

        def on_file_read(stream: Gio.InputStream, task: Gio.Task, _):
            try:
                input_stream = stream.read_finish(task)
                GdkPixbuf.Pixbuf.new_from_stream_async(
                    input_stream, None, on_pixbuf_ready
                )
                input_stream.close_async(GLib.PRIORITY_DEFAULT, None, None)
            except Exception as _:
                logger.error(
                    f"[CLIPBOARD] Failed to download html image from cliphist id: {cliphist_id}"
                )

        def decode_callback(proc: Gio.Subprocess, task: Gio.Task):
            # TODO: The image is just read and stored in memory, since the clipboard is
            #   updated on every new `cliphist list`, this could take some time on slow connections...
            #
            #   We can store these images in a cache file instead, will fix copying these since it current is returning an html tag instead
            try:
                _, stdout, stderr = proc.communicate_finish(task)
                img_src = re.search(
                    r'<img[^>]+src="([^"]+)"', stdout.get_data().decode("utf8")
                ).group(1)
                Gio.File.new_for_uri(img_src).read_async(
                    GLib.PRIORITY_DEFAULT, None, on_file_read, None
                )

            except Exception as _:
                logger.error(
                    f"[CLIPBOARD] Failed to decode html image from cliphist id: {cliphist_id}"
                )

        self.cliphist_decode(cliphist_id, decode_callback)

    def parse_string(self, cliphist_id: str):
        file_path = ""

        def on_pixbuf_ready(loader, result):
            nonlocal file_path
            try:
                self._decoded_clipboard_history[cliphist_id] = (
                    GdkPixbuf.Pixbuf.new_from_stream_finish(result)
                )
                self.emit("clipboard-data-ready", cliphist_id)
            except Exception as _:
                logger.error(f"[CLIPBOARD] Failed to read pixbuf for file: {file_path}")

        def callback(proc: Gio.Subprocess, task: Gio.Task):
            nonlocal file_path
            try:
                _, stdout, stderr = proc.communicate_finish(task)
                decoded_string = str(stdout.get_data().decode("utf-8"))
                if decoded_string.startswith("file://"):
                    decoded_string = decoded_string[7:]

                if not os.path.exists(decoded_string):
                    self._decoded_clipboard_history[cliphist_id] = decoded_string[
                        : self._length_cutoff
                    ]
                    self.emit("clipboard-data-ready", cliphist_id)
                    return

                elif decoded_string.startswith("/* XPM */"):
                    try:
                        loader = GdkPixbuf.PixbufLoader()
                        loader.write(stdout.get_data())
                        loader.close()
                        self._decoded_clipboard_history[cliphist_id] = (
                            loader.get_pixbuf()
                        )
                        self.emit("clipboard-data-ready", cliphist_id)
                    except Exception as e:
                        self._decoded_clipboard_history[cliphist_id] = decoded_string
                        self.emit("clipboard-data-ready", cliphist_id)
                    return

                # FIXME: python 3.13 introduced a new function guess_file_type, use that
                file_type = mimetypes.guess_type(decoded_string)[0]
                if not file_type:
                    self._decoded_clipboard_history[cliphist_id] = decoded_string
                    self.emit("clipboard-data-ready", cliphist_id)
                    return
                file_path = decoded_string
                match file_type:
                    case file_type if any(
                        fmt in file_type for fmt in SUPPORTED_FORMATS
                    ) or file_type in ["image/x-xpixmap", "image/x-xbitmap"]:
                        get_file_pixbuf_async(decoded_string, on_pixbuf_ready)

                    # We can do this, but we can do it async instead here
                    # case "image/svg+xml":
                    #     self._decoded_clipboard_history[cliphist_id] = (
                    #         Rsvg.Handle.new_from_file(decoded_string).get_pixbuf()
                    #     )
                    #     self.emit("clipboard-data-ready", cliphist_id)

                    case _:
                        self._decoded_clipboard_history[cliphist_id] = decoded_string
                        self.emit("clipboard-data-ready", cliphist_id)
            except Exception as e:
                print(e)

        self.cliphist_decode(cliphist_id, callback)

    def decode_clipboard(self):
        pattern = re.compile("\[\[ binary data .* \]\]")
        for cliphist_id in self._clipboard_history.keys():
            preview: str = self._clipboard_history[cliphist_id]

            if pattern.match(preview):
                self.parse_data_binary(cliphist_id)

            elif preview.startswith("<?xml") or preview.startswith("<svg"):
                self.parse_data_svg(cliphist_id)

            elif preview.startswith("<meta"):
                self.parse_html_tag(cliphist_id)

            else:
                self.parse_string(cliphist_id)

    @Property(dict, "readable")
    def clipboard_history(self) -> dict:
        return self._clipboard_history

    @Property(dict, "readable")
    def decoded_clipboard_history(self) -> dict:
        return self._decoded_clipboard_history
