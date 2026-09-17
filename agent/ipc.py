"""Transport-neutral JSON-lines protocol for all JARVIS clients."""
import json
import sys
from typing import IO
from .core import AgentResult, JarvisAgent
from .protocol import PROTOCOL_VERSION, event, request, response, validate


def _result_payload(result: AgentResult) -> dict:
    return {"text": result.text, "provider": result.provider, "tool_used": result.tool_used, "needs_confirmation": result.needs_confirmation}

class _DeltaEmitter:
    def __init__(self, writer, req_id=None): self._writer, self._req_id = writer, req_id
    def __call__(self, delta: str):
        try:
            self._writer.write(json.dumps(event("delta", request_id=self._req_id, text=delta), ensure_ascii=False) + "\n"); self._writer.flush()
        except (ValueError, OSError): pass


def handle_request(agent: JarvisAgent, req: dict) -> dict:
    validate(req); req_id = req.get("id"); kind = req.get("type", "message")
    try:
        if kind == "message":
            text = req.get("text")
            if not isinstance(text, str): raise ValueError("'text' must be a string")
            return response(req_id, "message", **_result_payload(agent.handle(text)), state=agent.state.state.value)
        if kind == "tool":
            name, args = req.get("tool"), req.get("args", [])
            if not isinstance(name, str) or not isinstance(args, list): raise ValueError("'tool' must be a string and 'args' a list")
            command = "/" + name + (" " + " ".join(map(str, args)) if args else "")
            return response(req_id, "message", **_result_payload(agent.handle(command)), state=agent.state.state.value)
        if kind == "tools": return response(req_id, "tools", tools=list(agent.tools.names()), state=agent.state.state.value)
        if kind == "state": return response(req_id, "state", state=agent.state.state.value)
        if kind == "clear_memory":
            session = getattr(agent, "session", None)
            if session is None: raise RuntimeError("Сессия недоступна для текущего провайдера")
            return response(req_id, "message", **_result_payload(AgentResult(session.clear(), agent.provider.name)), state=agent.state.state.value)
        if kind == "ping": return response(req_id, "pong", state=agent.state.state.value)
        raise ValueError(f"unknown request type: {kind!r}")
    except Exception as exc:
        agent.state.error(); return response(req_id, "error", message=str(exc), state=agent.state.state.value)


def serve_stream(agent: JarvisAgent, reader: IO[str], writer: IO[str]):
    provider = getattr(agent, "provider", None)
    def on_state(_old, new):
        try: writer.write(json.dumps(event("state", state=new.value), ensure_ascii=False) + "\n"); writer.flush()
        except (ValueError, OSError): pass
    agent.state.subscribe(on_state)
    for line in reader:
        line = line.strip()
        if not line: continue
        try: req = json.loads(line)
        except json.JSONDecodeError: req = None
        if not isinstance(req, dict): response_obj = event("error", message="invalid JSON request")
        else:
            emitter = _DeltaEmitter(writer, req.get("id"))
            if provider is not None and hasattr(provider, "on_delta"): provider.on_delta = emitter
            try: response_obj = handle_request(agent, req)
            finally:
                if provider is not None and hasattr(provider, "on_delta"): provider.on_delta = None
        writer.write(json.dumps(response_obj, ensure_ascii=False) + "\n"); writer.flush()


def serve_stdio(agent: JarvisAgent):
    for stream in (sys.stdin, sys.stdout):
        try: stream.reconfigure(encoding="utf-8", errors="strict")
        except (AttributeError, ValueError): pass
    serve_stream(agent, sys.stdin, sys.stdout)


def serve_tcp(agent: JarvisAgent, host: str = "127.0.0.1", port: int = 8765):
    import socket
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); server.bind((host, port)); server.listen(4)
        print(f"JARVIS IPC v{PROTOCOL_VERSION} listening on {host}:{port}", file=sys.stderr)
        while True:
            conn, _addr = server.accept()
            with conn, conn.makefile("r", encoding="utf-8") as r, conn.makefile("w", encoding="utf-8") as w: serve_stream(agent, r, w)
