"""
Blocking JSON-over-HTTP for worker threads, on the standard library.

`requests` (with urllib3, charset_normalizer and idna) costs about 8 MB more
than urllib, and importing it on a worker thread holds the GIL long enough
to stall the GTK loop at startup.
"""

import json
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "fabric-config/1.0"


def get_json(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10,
) -> Any:
    """GET `url` and parse the JSON body. Raises `urllib.error.HTTPError` on a
    non-2xx status and `URLError`/`OSError`/`ValueError` on other failures."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, **(headers or {})}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)
