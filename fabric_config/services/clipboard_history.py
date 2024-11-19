import re
from typing import Callable
import mimetypes as mt

import gi
from fabric import Fabricator, Property, Service, Signal


gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Rsvg", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib, Rsvg


def get_file_pixbuf_async(file_path: str, callback: Callable):
    def on_file_read(stream: Gio.InputStream, task: Gio.Task, _):
        try:
            input_stream = stream.read_finish(task)
            GdkPixbuf.Pixbuf.new_from_stream_async(input_stream, None, callback)
        except Exception as e:
            print(e)

    file: Gio.File = Gio.File.new_for_path(file_path)
    file.read_async(GLib.PRIORITY_DEFAULT, None, on_file_read, None)
    # )
    # Gio.DataOutputStream.new_


class ClipboardHistory(Service):
    @Signal
    def clipboard_deleted(self, cliphist_id: str) -> str: ...
    @Signal
    def clipboard_copied(self, cliphist_id: str) -> str: ...
    @Signal
    def clipboard_data_ready(self, cliphist_id: str) -> str: ...

    def __init__(self):
        self._clipboard_history = {}
        self._decoded_clipboard_history = {}
        super().__init__()
        self.wl_paste_watcher = Fabricator(
            poll_from="wl-paste --watch echo", stream=True, interval=-1
        )
        self.wl_paste_watcher.connect("changed", lambda *_: self.cliphist_list())

    def cliphist_list(self):
        def callback(proc: Gio.Subprocess, task: Gio.Task):
            try:
                _, stdout, stderr = proc.communicate_utf8_finish(task)
                self._clipboard_history = {
                    key: value
                    for x in stdout.split("\n")[:-1]
                    for key, value in [x.split("\t", 1)]
                }
                self.notify("clipboard-history")
            except Exception as e:
                print(e)

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
        def wl_copy_callback(proc: Gio.OutputStream, task: Gio.Task):
            proc.write_bytes_finish(task)
            proc.close()
            self.emit("clipboard-copied", cliphist_id)

        def cliphist_decode_callback(proc: Gio.Subprocess, task: Gio.Task):
            try:
                _, stdout, stderr = proc.communicate_finish(task)
                in_pipe.write_bytes_async(stdout, 0, None, wl_copy_callback)
            except Exception as e:
                print("error faild")

        process: Gio.Subprocess = Gio.Subprocess.new(
            ["wl-copy"],
            Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
        )  # type: ignore
        in_pipe: Gio.OutputStream = process.get_stdin_pipe()
        self.cliphist_decode(cliphist_id, cliphist_decode_callback)

    def cliphist_delete(self, cliphist_id: str):
        self.cliphist_id = cliphist_id

        process: Gio.Subprocess = Gio.Subprocess.new(
            ["cliphist", "delete"],
            Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
        )  # type: ignore

        in_pipe: Gio.OutputStream = process.get_stdin_pipe()
        out_stream = Gio.DataOutputStream.new(in_pipe)
        out_stream.put_string(
            f"{cliphist_id}\t{self._clipboard_history[cliphist_id]}\n", None
        )
        self.emit("clipboard-deleted", self.cliphist_id)

    def parse_data_svg(self, cliphist_id: str):
        def callback(proc: Gio.Subprocess, task: Gio.Task):
            try:
                _, stdout, stderr = proc.communicate_finish(task)
                self._decoded_clipboard_history[cliphist_id] = (
                    Rsvg.Handle.new_from_data(stdout.get_data()).get_pixbuf()
                )
                self.emit("clipboard-data-ready", cliphist_id)
            except Exception as e:
                print("failed to get svg", e)

        self.cliphist_decode(cliphist_id, callback)

    def parse_data_binary(self, cliphist_id: str):
        # preview = self._clipboard_history[cliphist_id]
        # info = preview.split()
        # _size = info[3:5]
        # data_type = info[5]
        # image_dimensions = tuple(map(int, info[6].split("x")))

        def callback(pixbuf_loader: GdkPixbuf.Pixbuf, task: Gio.Task):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_stream_finish(task)
                self._decoded_clipboard_history[cliphist_id] = pixbuf
                self.emit("clipboard-data-ready", cliphist_id)

            except Exception as e:
                print("error failed", e)

        process: Gio.Subprocess = Gio.Subprocess.new(
            ["cliphist", "decode", str(cliphist_id)],
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
        )  # type: ignore

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
            except Exception as e:
                print(e)

        def decode_callback(proc: Gio.Subprocess, task: Gio.Task):
            try:
                _, stdout, stderr = proc.communicate_finish(task)
                img_src = re.search(
                    r'<img[^>]+src="([^"]+)"', stdout.get_data().decode("utf8")
                ).group(1)

                Gio.File.new_for_uri(img_src).read_async(
                    GLib.PRIORITY_DEFAULT, None, on_file_read, None
                )

            except Exception as e:
                print("error, failed", e)

        self.cliphist_decode(cliphist_id, decode_callback)

    def parse_file_path(self, cliphist_id: str):
        def on_pixbuf_ready(loader, result):
            try:
                self._decoded_clipboard_history[cliphist_id] = (
                    GdkPixbuf.Pixbuf.new_from_stream_finish(result)
                )
                print(f"sending signal for id {cliphist_id}")
                self.emit("clipboard-data-ready", cliphist_id)
            except Exception as e:
                print(e)

        def callback(proc: Gio.Subprocess, task: Gio.Task):
            try:
                _, stdout, stderr = proc.communicate_finish(task)
                file_path = str(stdout.get_data().decode("utf-8"))
                # FIXME: python 3.13 introduced a new function guess_file_type, use that
                file_type = mt.guess_type(file_path)[0]

                if not file_type:
                    self._decoded_clipboard_history[cliphist_id] = file_path
                    self.emit("clipboard-data-ready", cliphist_id)
                elif file_type.startswith("image/") and file_type.endswith(
                    ("jpeg", "tiff", "png", "ico", "bmp")
                ):
                    get_file_pixbuf_async(file_path, on_pixbuf_ready)
                elif file_type == "image/svg+xml":
                    self._decoded_clipboard_history[cliphist_id] = (
                        Rsvg.Handle.new_from_file(file_path).get_pixbuf()
                    )
                    self.emit("clipboard-data-ready", cliphist_id)
                elif file_type == "image/gif":
                    # TODO: Make async
                    self._decoded_clipboard_history[cliphist_id] = (
                        GdkPixbuf.PixbufAnimation.new_from_file(
                            file_path
                        ).get_static_image()
                    )
                    self.emit("clipboard-data-ready", cliphist_id)
                    print("GOT?")
                else:
                    self._decoded_clipboard_history[cliphist_id] = file_path
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
            # I wont let clipboard pull files outside of /home/
            elif preview.startswith("/home/"):
                self.parse_file_path(cliphist_id)
            else:
                self.parse_file_path(cliphist_id)

    @Property(dict, "readable")
    def clipboard_history(self) -> dict:
        return self._clipboard_history

    @Property(dict, "readable")
    def decoded_clipboard_history(self) -> dict:
        return self._decoded_clipboard_history

