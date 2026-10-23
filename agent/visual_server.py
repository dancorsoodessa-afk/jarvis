"""Serve the local Three.js reactor and live UI state over loopback only."""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable


def _scene_file() -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    candidate = bundle_root / "ui" / "jarvis_3d.html"
    if candidate.is_file():
        return candidate
    return Path(__file__).resolve().parent.parent / "ui" / "jarvis_3d.html"


def start_visual_server(state_provider: Callable[[], dict]):
    scene_path = _scene_file()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/state":
                body = json.dumps(state_provider(), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path not in {"/", "/jarvis_3d.html"}:
                self.send_error(404)
                return
            try:
                body = scene_path.read_bytes()
            except OSError:
                self.send_error(500, "3D scene asset is missing")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, name="jarvis-3d-server", daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}/"
