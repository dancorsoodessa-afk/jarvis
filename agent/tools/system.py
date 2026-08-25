import platform
import shutil

def status():
    return {
        "os": platform.platform(),
        "python": platform.python_version(),
        "disk_free_gb": round(shutil.disk_usage(".").free / 1024**3, 1),
    }
