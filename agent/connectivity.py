"""Internet availability gate for SUPERMAN voice features.

Voice input and speech output are intentionally unavailable without internet.
Text UI remains available; this module performs a small cached HTTPS probe.
"""
from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request

_CACHE_TTL_SECONDS = 2.0
_PROBE_TIMEOUT_SECONDS = 1.0
_PROBE_URLS = (
    "https://www.cloudflare.com/cdn-cgi/trace",
    "https://www.google.com/generate_204",
)
_LOCK = threading.Lock()
_cached_at = 0.0
_cached_value = False


def internet_available(force: bool = False) -> bool:
    """Return whether an external HTTPS endpoint is reachable.

    Results are cached briefly so UI status checks do not repeatedly probe the
    network. force=True is intended for the background connectivity monitor.
    """
    global _cached_at, _cached_value
    now = time.monotonic()
    with _LOCK:
        if not force and now - _cached_at < _CACHE_TTL_SECONDS:
            return _cached_value

        online = False
        for url in _PROBE_URLS:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "SUPERMAN/1.0"},
                method="GET",
            )
            try:
                with urllib.request.urlopen(request, timeout=_PROBE_TIMEOUT_SECONDS) as response:
                    status = int(getattr(response, "status", 200))
                    if 200 <= status < 500:
                        online = True
                        break
            except urllib.error.HTTPError as exc:
                # A 4xx response still proves that the internet connection works.
                if 200 <= exc.code < 500:
                    online = True
                    break
            except (urllib.error.URLError, TimeoutError, OSError):
                continue

        _cached_value = online
        _cached_at = time.monotonic()
        return online
