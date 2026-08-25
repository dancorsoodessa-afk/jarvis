"""JSON-lines IPC for the Flutter UI (Flutter <-> Python agent core).

Protocol: one JSON object per line, UTF-8.

  Request : {"id": 1, "type": "message", "text": "привет"}
            {"id": 2, "type": "tool", "tool": "search", "args": ["*.txt", "C:\\"]}
  Response: {"id": 1, "type": "message",
             "text": "...", "provider": "cloud",
             "tool_used": null, "needs_confirmation": false}
            {"id": null, "type": "error", "message": "..."}

Default transport is stdin/stdout so Flutter can spawn the agent as a child
process with Process.start(). TCP transport is available for remote UIs.
"""

import json
import sys
from typing import IO

from .core import AgentResult, JarvisAgent


def _result_payload(result: AgentResult) -> dict:
    return {
        "text": result.text,
        "provider": result.provider,
        "tool_used": result.tool_used,
        "needs_confirmation": result.needs_confirmation,
    }


def handle_request(agent: JarvisAgent, req: dict) -> dict:
    """One request -> one response dict. Pure function, easy to test."""
    req_id = req.get("id")
    req_type = req.get("type", "message")
    try:
        if req_type == "message":
            text = req.get("text")
            if not isinstance(text, str):
                raise ValueError("'text' must be a string")
            return {"id": req_id, "type": "message", **_result_payload(agent.handle(text))}
        if req_type == "tool":
            name = req.get("tool")
            args = req.get("args", [])
            if not isinstance(name, str) or not isinstance(args, list):
                raise ValueError("'tool' must be a string and 'args' a list")
            command = "/" + name + (" " + " ".join(map(str, args)) if args else "")
            return {"id": req_id, "type": "message", **_result_payload(agent.handle(command))}
        if req_type == "tools":
            return {"id": req_id, "type": "tools", "tools": list(agent.tools.names())}
        if req_type == "ping":
            return {"id": req_id, "type": "pong"}
        raise ValueError(f"unknown request type: {req_type!r}")
    except Exception as exc:
        return {"id": req_id, "type": "error", "message": str(exc)}


def serve_stream(agent: JarvisAgent, reader: IO[str], writer: IO[str]):
    """Process JSON-lines requests until EOF."""
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
            response = handle_request(agent, req)
        writer.write(json.dumps(response, ensure_ascii=False) + "\n")
        writer.flush()


def serve_stdio(agent: JarvisAgent):
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
            with conn, conn.makefile("r", encoding="utf-8") as r, \
                    conn.makefile("w", encoding="utf-8") as w:
                serve_stream(agent, r, w)
