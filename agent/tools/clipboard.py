"""Clipboard get/set. Tries tkinter (bundled with Python), then OS tools."""

import shutil
import subprocess
import sys


def _tkinter(method, text=None):
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    try:
        if method == "get":
            return root.clipboard_get()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()  # keeps content after the window closes
    finally:
        root.destroy()


def get() -> str:
    try:
        return _tkinter("get")
    except Exception:
        pass
    if sys.platform == "win32":
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            return out.stdout.rstrip("\r\n")
    for tool, cmd in (("xclip", ["xclip", "-selection", "clipboard", "-o"]),
                      ("wl-paste", ["wl-paste"]),
                      ("pbpaste", ["pbpaste"])):
        if shutil.which(tool):
            return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    raise RuntimeError("No clipboard backend (tkinter/xclip/wl-paste/pbpaste)")


def set(text: str) -> str:
    try:
        _tkinter("set", text)
        return "Clipboard set"
    except Exception:
        pass
    if sys.platform == "win32":
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $input"],
            input=text, capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0:
            return "Clipboard set"
    for tool, cmd in (("xclip", ["xclip", "-selection", "clipboard"]),
                      ("wl-copy", ["wl-copy"]),
                      ("pbcopy", ["pbcopy"])):
        if shutil.which(tool):
            subprocess.run(cmd, input=text, text=True, timeout=10, check=True)
            return "Clipboard set"
    raise RuntimeError("No clipboard backend (tkinter/xclip/wl-copy/pbcopy)")
