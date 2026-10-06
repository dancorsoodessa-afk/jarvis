"""Small OS-backed secret storage helper for JARVIS settings."""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import os


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


_PREFIX = "DPAPI1:"


def _dpapi_protect(value: str) -> str:
    if os.name != "nt":
        return ""
    raw = value.encode("utf-8")
    in_buf = ctypes.create_string_buffer(raw)
    blob_in = _DATA_BLOB(
        ctypes.sizeof(in_buf),
        ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_byte)),
    )
    blob_out = _DATA_BLOB()
    crypt = ctypes.windll.crypt32.CryptProtectData
    crypt.argtypes = [
        ctypes.POINTER(_DATA_BLOB),
        ctypes.wintypes.LPCWSTR,
        ctypes.POINTER(_DATA_BLOB),
        ctypes.wintypes.LPVOID,
        ctypes.wintypes.LPVOID,
        ctypes.wintypes.DWORD,
        ctypes.POINTER(_DATA_BLOB),
    ]
    crypt.restype = ctypes.wintypes.BOOL
    if not crypt(ctypes.byref(blob_in), "JARVIS settings", None, None, None, 0, ctypes.byref(blob_out)):
        raise ctypes.WinError()
    try:
        encrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return _PREFIX + base64.b64encode(encrypted).decode("ascii")


def _dpapi_unprotect(value: str) -> str:
    encoded = value[len(_PREFIX):]
    encrypted = base64.b64decode(encoded)
    in_buf = ctypes.create_string_buffer(encrypted)
    blob_in = _DATA_BLOB(
        len(encrypted),
        ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_byte)),
    )
    blob_out = _DATA_BLOB()
    crypt = ctypes.windll.crypt32.CryptUnprotectData
    crypt.argtypes = [
        ctypes.POINTER(_DATA_BLOB),
        ctypes.POINTER(ctypes.wintypes.LPWSTR),
        ctypes.POINTER(_DATA_BLOB),
        ctypes.wintypes.LPVOID,
        ctypes.wintypes.LPVOID,
        ctypes.wintypes.DWORD,
        ctypes.POINTER(_DATA_BLOB),
    ]
    crypt.restype = ctypes.wintypes.BOOL
    if not crypt(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData).decode("utf-8").rstrip("\x00")
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def protect_secret(value: str) -> str:
    value = str(value or "")
    if not value:
        return ""
    if value.startswith(_PREFIX):
        return value
    if os.name == "nt":
        return _dpapi_protect(value)
    # Non-Windows development/test environments have no equivalent user-bound
    # credential store here; keep compatibility rather than inventing weak crypto.
    return value


def unprotect_secret(value: str) -> str:
    value = str(value or "")
    if not value or not value.startswith(_PREFIX):
        return value
    if os.name != "nt":
        return ""
    try:
        return _dpapi_unprotect(value)
    except Exception:
        # A corrupt/unreadable secret must not crash application startup.
        return ""
