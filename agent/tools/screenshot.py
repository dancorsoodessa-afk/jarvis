"""Screenshots. Uses PIL if installed, else a platform CLI tool."""

import shutil
import subprocess
import time
from pathlib import Path

_DIR_TOOLS = ["gnome-screenshot", "scrot", "grim", "import"]


def capture(path: str | None = None) -> str:
    """Take a screenshot, save it, return the file path."""
    target = Path(path or f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png").expanduser()

    try:
        from PIL import ImageGrab
    except ImportError:
        ImageGrab = None

    if ImageGrab is not None:
        ImageGrab.grab().save(target)
        return str(target)

    if shutil.which("gnome-screenshot"):
        cmd = ["gnome-screenshot", "-f", str(target)]
    elif shutil.which("scrot"):
        cmd = ["scrot", str(target)]
    elif shutil.which("grim"):
        cmd = ["grim", str(target)]
    elif shutil.which("import"):  # ImageMagick, X11
        cmd = ["import", "-window", "root", str(target)]
    else:
        raise RuntimeError("No screenshot backend: install Pillow or gnome-screenshot/scrot/grim")
    subprocess.run(cmd, check=True, capture_output=True, timeout=15)
    return str(target)
