from __future__ import annotations

import urllib.error

from agent import connectivity


class _Response:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _reset_cache():
    connectivity._cached_at = 0.0
    connectivity._cached_value = False


def test_internet_available_when_https_probe_succeeds(monkeypatch):
    _reset_cache()
    monkeypatch.setattr(connectivity.urllib.request, "urlopen", lambda *a, **k: _Response())
    assert connectivity.internet_available(force=True) is True


def test_internet_unavailable_when_all_https_probes_fail(monkeypatch):
    _reset_cache()

    def fail(*args, **kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(connectivity.urllib.request, "urlopen", fail)
    assert connectivity.internet_available(force=True) is False


def test_probe_result_is_cached(monkeypatch):
    _reset_cache()
    calls = []

    def succeed(*args, **kwargs):
        calls.append(1)
        return _Response()

    monkeypatch.setattr(connectivity.urllib.request, "urlopen", succeed)
    assert connectivity.internet_available(force=True) is True
    first_count = len(calls)
    assert connectivity.internet_available() is True
    assert len(calls) == first_count
