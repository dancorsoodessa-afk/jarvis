"""Local secret storage using Windows DPAPI when available."""
from __future__ import annotations
import base64
import ctypes
import os
from pathlib import Path
from ctypes import wintypes

APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "JARVIS"
SECRET_FILE = APP_DIR / "secrets.json"

def _dpapi(data: bytes, decrypt: bool = False) -> bytes:
    if os.name != "nt":
        raise RuntimeError("DPAPI доступен только в Windows")
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]
    CryptProtectData = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    CryptProtectData.argtypes = [ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(DATA_BLOB),
                                 wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    CryptProtectData.restype = wintypes.BOOL
    src_buf = ctypes.create_string_buffer(data)
    src = DATA_BLOB(len(data), ctypes.cast(src_buf, ctypes.POINTER(ctypes.c_byte)))
    out = DATA_BLOB()
    if not CryptProtectData(ctypes.byref(src), "JARVIS", None, None, None, 0, ctypes.byref(out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)

def save_secret(name: str, value: str) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    import json
    data = {}
    if SECRET_FILE.exists():
        try:
            data = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    encrypted = _dpapi(value.encode("utf-8"))
    data[name] = base64.b64encode(encrypted).decode("ascii")
    SECRET_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

def load_secret(name: str, default: str = "") -> str:
    if not SECRET_FILE.exists():
        return default
    try:
        import json
        data = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
        raw = base64.b64decode(str(data.get(name, "")))
        return _dpapi(raw, decrypt=True).decode("utf-8")
    except Exception:
        return default

def delete_secret(name: str) -> None:
    if not SECRET_FILE.exists():
        return
    try:
        import json
        data = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
        data.pop(name, None)
        SECRET_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
