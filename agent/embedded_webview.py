"""Embed the local Three.js reactor in the Windows Tkinter window using Edge app mode.

No additional runtime package is required. The Edge window uses a private profile
and is re-parented as a native child window of the Tkinter scene host.
"""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import tempfile
import time
from ctypes import wintypes
from pathlib import Path


class EmbeddedEdgeView:
    """Host a real Chromium/WebGL Edge app window inside a native parent HWND."""

    def __init__(self, parent_hwnd: int, url: str) -> None:
        if os.name != "nt":
            raise RuntimeError("Встроенная WebGL-сцена поддерживается только в Windows.")
        if not parent_hwnd:
            raise ValueError("Не задан контейнер для встроенной 3D-сцены.")
        self.parent_hwnd = int(parent_hwnd)
        self.url = str(url)
        self.process: subprocess.Popen | None = None
        self.hwnd: int | None = None
        self._profile_dir: Path | None = None
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)

    @staticmethod
    def find_edge() -> str:
        """Find the installed Microsoft Edge browser without relying on PATH."""
        from_path = shutil.which("msedge.exe") or shutil.which("msedge")
        if from_path:
            return from_path
        roots = (
            os.environ.get("PROGRAMFILES(X86)", ""),
            os.environ.get("PROGRAMFILES", ""),
            os.environ.get("LOCALAPPDATA", ""),
        )
        for root in roots:
            if root:
                candidate = Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
                if candidate.is_file():
                    return str(candidate)
        raise RuntimeError(
            "Microsoft Edge не найден. Установите Edge, чтобы встроить настоящий WebGL-реактор в окно JARVIS."
        )

    def start(self, timeout: float = 15.0) -> None:
        if self.hwnd:
            return
        edge = self.find_edge()
        self._profile_dir = Path(tempfile.mkdtemp(prefix="jarvis-reactor-"))
        args = [
            edge,
            f"--user-data-dir={self._profile_dir}",
            f"--app={self.url}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-mode",
            "--disable-extensions",
            "--window-size=900,600",
        ]
        try:
            process = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            self.process = process
            deadline = time.monotonic() + max(3.0, min(30.0, timeout))
            while time.monotonic() < deadline:
                # Keep a local process reference: close() may run on the Tk thread
                # while this worker is waiting for Edge to create its window.
                if process.poll() is not None:
                    raise RuntimeError("Microsoft Edge завершился до открытия 3D-сцены.")
                hwnd = self._find_main_window(process.pid)
                if hwnd:
                    self._embed(hwnd)
                    self.hwnd = hwnd
                    return
                time.sleep(0.1)
            raise TimeoutError("Edge запустился, но окно WebGL-реактора не найдено за отведённое время.")
        except Exception:
            self.close()
            raise

    def _find_main_window(self, process_id: int) -> int | None:
        user32 = self._user32
        found: list[int] = []
        enum_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetWindow.restype = wintypes.HWND
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.restype = ctypes.c_int
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.IsWindow.restype = wintypes.BOOL

        def visit(hwnd, _lparam):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != process_id or user32.GetWindow(hwnd, 4):  # GW_OWNER
                return True
            if not user32.IsWindow(hwnd):
                return True
            class_name = ctypes.create_unicode_buffer(128)
            user32.GetClassNameW(hwnd, class_name, len(class_name))
            if class_name.value.startswith("Chrome_WidgetWin"):
                found.append(int(hwnd))
                return False
            return True

        user32.EnumWindows.argtypes = [enum_callback, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.EnumWindows(enum_callback(visit), 0)
        return found[0] if found else None

    def _embed(self, hwnd: int) -> None:
        user32 = self._user32
        hwnd_t = wintypes.HWND
        get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        set_style = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        get_style.argtypes = [hwnd_t, ctypes.c_int]
        get_style.restype = ctypes.c_ssize_t
        set_style.argtypes = [hwnd_t, ctypes.c_int, ctypes.c_ssize_t]
        set_style.restype = ctypes.c_ssize_t
        user32.SetParent.argtypes = [hwnd_t, hwnd_t]
        user32.SetParent.restype = hwnd_t
        user32.SetWindowPos.argtypes = [
            hwnd_t, hwnd_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT
        ]
        user32.SetWindowPos.restype = wintypes.BOOL

        GWL_STYLE, GWL_EXSTYLE = -16, -20
        WS_CHILD, WS_VISIBLE = 0x40000000, 0x10000000
        WS_POPUP, WS_CAPTION, WS_THICKFRAME = 0x80000000, 0x00C00000, 0x00040000
        WS_SYSMENU, WS_MINIMIZEBOX, WS_MAXIMIZEBOX = 0x00080000, 0x00020000, 0x00010000
        WS_EX_APPWINDOW, WS_EX_TOOLWINDOW = 0x00040000, 0x00000080
        style = get_style(hwnd, GWL_STYLE)
        style = (style | WS_CHILD | WS_VISIBLE) & ~(
            WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
        )
        set_style(hwnd, GWL_STYLE, style)
        ex_style = get_style(hwnd, GWL_EXSTYLE)
        set_style(hwnd, GWL_EXSTYLE, (ex_style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW)
        ctypes.set_last_error(0)
        previous_parent = user32.SetParent(hwnd, self.parent_hwnd)
        if not previous_parent and ctypes.get_last_error():
            raise ctypes.WinError(ctypes.get_last_error())
        # SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW
        flags = 0x0004 | 0x0010 | 0x0020 | 0x0040
        if not user32.SetWindowPos(hwnd, None, 0, 0, 1, 1, flags):
            raise ctypes.WinError(ctypes.get_last_error())

    def resize(self, width: int, height: int) -> None:
        if not self.hwnd:
            return
        flags = 0x0004 | 0x0010 | 0x0040  # SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW
        if not self._user32.SetWindowPos(
            wintypes.HWND(self.hwnd), None, 0, 0, max(1, int(width)), max(1, int(height)), flags
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        hwnd, process = self.hwnd, self.process
        self.hwnd = None
        if hwnd:
            try:
                self._user32.PostMessageW(wintypes.HWND(hwnd), 0x0010, 0, 0)  # WM_CLOSE
            except Exception:
                pass
        if process is not None and process.poll() is None:
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    process.kill()
        if self._profile_dir:
            shutil.rmtree(self._profile_dir, ignore_errors=True)
            self._profile_dir = None
        self.process = None
