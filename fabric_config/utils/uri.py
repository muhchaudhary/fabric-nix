from gi.repository import GLib


def file_uri_to_path(uri: str) -> str:
    """
    Convert a file:// URI to a local path, decoding escapes such as %20.
    Strings that aren't valid file URIs are returned unchanged.
    """
    try:
        path, _ = GLib.filename_from_uri(uri)
        return path
    except GLib.Error:
        return uri
