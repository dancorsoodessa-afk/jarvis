from pathlib import Path
import os
import unittest
from unittest.mock import patch

from agent.embedded_webview import EmbeddedEdgeView


ROOT = Path(__file__).resolve().parents[1]


def test_desktop_uses_embedded_reactor_instead_of_external_browser():
    source = (ROOT / "jarvis_desktop.py").read_text(encoding="utf-8")
    assert "from agent.embedded_webview import EmbeddedEdgeView" in source
    assert "view = EmbeddedEdgeView(parent_hwnd, self._visual_url)" in source
    assert 'self.scene_label.bind("<Configure>", self._resize_embedded_3d)' in source
    assert "self._embedded_webview.close()" not in source  # shutdown uses the guarded local reference
    assert "webbrowser.open(" not in source


def test_embedded_reactor_is_loopback_only_and_reparents_edge_window():
    source = (ROOT / "agent/embedded_webview.py").read_text(encoding="utf-8")
    assert 'f"--app={self.url}"' in source
    assert "user32.SetParent(hwnd, self.parent_hwnd)" in source
    assert "SetWindowPos" in source
    assert "GROQ_API_KEY" not in source  # the view has no separate network dependency


def test_embedded_view_refuses_non_windows_before_loading_win32_api():
    if os.name == "nt":
        return
    with patch("agent.embedded_webview.ctypes.WinDLL", create=True) as win_dll:
        try:
            EmbeddedEdgeView(1, "http://127.0.0.1:1234/").start()
        except RuntimeError as exc:
            assert "только в Windows" in str(exc)
        else:
            raise AssertionError("The Windows-only embedded WebView must reject non-Windows hosts.")
        win_dll.assert_not_called()


def test_embedded_view_requires_a_parent_window():
    with patch("agent.embedded_webview.os.name", "nt"):
        with patch("agent.embedded_webview.ctypes.WinDLL", create=True):
            try:
                EmbeddedEdgeView(0, "http://127.0.0.1:1234/")
            except ValueError as exc:
                assert "контейнер" in str(exc)
            else:
                raise AssertionError("A missing parent HWND must be rejected.")
