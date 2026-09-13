"""JSON-lines IPC for desktop/mobile clients."""
from __future__ import annotations

import json
import sys
from typing import IO

from .core import JarvisAgent


class _DeltaEmitter:
    def __init__(self, writer: IO[str], req_id):
        self.writer = writer
        self.req_id = req_id

    def __call__(self, text: str):
        self.writer.write(json.dumps({"id": self.req_id, "type": "delta", "text": text}, ensure_ascii=False) + "\n")
        self.writer.flush()


def _error(req_id, message: str) -> dict:
    return {"id": req_id, "type": "error", "message": message}


def handle_request(agent: JarvisAgent, req: dict) -> dict:
    req_id = req.get("id")
    kind = req.get("type", "message")

    if kind == "ping":
        return {"id": req_id, "type": "pong"}

    if kind == "tools":
        return {"id": req_id, "type": "tools", "tools": list(agent.tools.names())}

    if kind == "message":
        text = req.get("text", "")
        if not isinstance(text, str):
            return _error(req_id, "Поле text должно быть строкой")
        result = agent.handle(text)
        return {
            "id": req_id,
            "type": "message",
            "text": result.text,
            "provider": result.provider,
            "tool": result.tool_used,
            "needs_confirmation": result.needs_confirmation,
        }

    if kind == "tool":
        name = req.get("tool")
        if not isinstance(name, str):
            return _error(req_id, "Поле tool должно быть строкой")
        args = req.get("args", [])
        if not isinstance(args, list):
            return _error(req_id, "Поле args должно быть списком")
        try:
            result = agent._run_tool(name, *args)
        except Exception as exc:
            return _error(req_id, str(exc))
        return {
            "id": req_id,
            "type": "message",
            "text": result.text,
            "provider": result.provider,
            "tool_used": result.tool_used,
            "needs_confirmation": result.needs_confirmation,
        }

    if kind == "clear_memory":
        # Memory clearing is a session-level operation; IPC does not expose a
        # session object, so fail explicitly rather than silently mutating data.
        return _error(req_id, "Сессия недоступна для очистки памяти")

    return _error(req_id, f"Неизвестный тип запроса: {kind}")


def serve_stream(agent: JarvisAgent, reader: IO[str], writer: IO[str]):
    """Process JSON-lines requests until EOF."""
    provider = getattr(agent, "provider", None)
    for line in reader:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            req = None
        if not isinstance(req, dict):
            response = {"id": None, "type": "error", "message": "invalid JSON request"}
        else:
            emitter = _DeltaEmitter(writer, req.get("id"))
            if provider is not None and hasattr(provider, "on_delta"):
                provider.on_delta = emitter
            try:
                response = handle_request(agent, req)
            finally:
                if provider is not None and hasattr(provider, "on_delta"):
                    provider.on_delta = None
        writer.write(json.dumps(response, ensure_ascii=False) + "\n")
        writer.flush()


def serve_stdio(agent: JarvisAgent):
    # Windows defaults to cp1252 for console pipes; JSON IPC is explicitly UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="strict")
    serve_stream(agent, sys.stdin, sys.stdout)


def serve_tcp(agent: JarvisAgent, host: str = "127.0.0.1", port: int = 8765):
    import socket
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen(1)
        print(f"JARVIS IPC listening on {host}:{port}", file=sys.stderr)
        while True:
            conn, _addr = server.accept()
            with conn, conn.makefile("r", encoding="utf-8") as r, conn.makefile("w", encoding="utf-8") as w:
                serve_stream(agent, r, w)
