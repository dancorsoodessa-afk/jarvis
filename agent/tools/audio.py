"""Volume control: pycaw on Windows (optional dep), amixer/pactl on Linux."""

import shutil
import subprocess
import sys


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"command failed: {cmd[0]}")
    return result.stdout.strip()


def _windows_volume():
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    except ImportError:
        raise RuntimeError(
            "Windows volume control needs optional deps: pip install jarvis-agent[windows-audio]"
        )
    devices = AudioUtilities.GetSpeakers()
    endpoint = getattr(devices, "EndpointVolume", None)
    if endpoint is not None:
        return endpoint
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    try:
        return interface.QueryInterface(IAudioEndpointVolume)
    except AttributeError:
        return cast(interface, POINTER(IAudioEndpointVolume))


def get_volume() -> str:
    if sys.platform == "win32":
        return f"{round(_windows_volume().GetMasterVolumeLevelScalar() * 100)}%"
    if shutil.which("amixer"):
        return _run(["amixer", "get", "Master"])
    if shutil.which("pactl"):
        return _run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
    raise RuntimeError("No supported mixer found (amixer/pactl)")


def set_volume(percent: str) -> str:
    level = int(percent)
    if not 0 <= level <= 100:
        raise ValueError("Volume must be 0-100")
    if sys.platform == "win32":
        volume = _windows_volume()
        if volume.GetMute():
            volume.SetMute(0, None)
        volume.SetMasterVolumeLevelScalar(level / 100, None)
    elif shutil.which("amixer"):
        _run(["amixer", "set", "Master", f"{level}%"])
    elif shutil.which("pactl"):
        _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"])
    else:
        raise RuntimeError("No supported mixer found (amixer/pactl)")
    return f"Volume set to {level}%"

def change_volume(delta: str) -> str:
    """Increase/decrease Windows master volume by a relative percentage."""
    step = int(delta)
    if step == 0:
        return get_volume()
    if sys.platform == "win32":
        volume = _windows_volume()
        current = round(float(volume.GetMasterVolumeLevelScalar()) * 100)
        target = max(0, min(100, current + step))
        if volume.GetMute() and step > 0:
            volume.SetMute(0, None)
        volume.SetMasterVolumeLevelScalar(target / 100, None)
        return f"Громкость: {target}%"
    raise RuntimeError("Относительное изменение громкости поддерживается только в Windows")
