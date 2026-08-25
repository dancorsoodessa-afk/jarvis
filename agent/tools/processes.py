"""Process listing and termination (stdlib only). Kill needs confirm=True."""

import csv
import io
import os
import signal
import subprocess
import sys
from pathlib import Path

MAX_LIST = 30


def list_processes(name_filter: str = "") -> list[dict]:
    """Return running processes [{pid, name}], optionally filtered by substring."""
    if sys.platform == "win32":
        out = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True, text=True, timeout=15,
        ).stdout
        procs = [
            {"pid": int(row[1]), "name": row[0]}
            for row in csv.reader(io.StringIO(out)) if len(row) >= 2
        ]
    else:
        procs = []
        for pid in filter(str.isdigit, os.listdir("/proc")):
            try:
                name = Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()
            except OSError:
                continue
            procs.append({"pid": int(pid), "name": name})
    if name_filter:
        procs = [p for p in procs if name_filter.lower() in p["name"].lower()]
    procs.sort(key=lambda p: p["name"].lower())
    return procs[:MAX_LIST]


def kill_process(pid: str) -> str:
    """Terminate a process by PID. Must be registered with confirm=True."""
    pid_int = int(pid)
    if pid_int <= 0 or pid_int == os.getpid():
        raise ValueError(f"Refusing to kill PID {pid_int}")
    if sys.platform == "win32":
        result = subprocess.run(
            ["taskkill", "/PID", str(pid_int), "/F"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    else:
        os.kill(pid_int, signal.SIGTERM)
    return f"Process {pid_int} terminated"
