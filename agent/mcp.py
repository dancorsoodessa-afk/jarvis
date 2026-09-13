"""Minimal MCP client over a stdio JSON-RPC transport.

This is intentionally dependency-free. It supports initialize, tools/list and
one-shot tools/call against a configured MCP server command.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass
class MCPServer:
    command: list[str]
    cwd: str | None = None
    timeout: float = 30.0


class MCPClient:
    def __init__(self, server: MCPServer):
        self.server = server
        self._next_id = 1

    def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        proc = subprocess.Popen(
            self.server.command,
            cwd=self.server.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            assert proc.stdin is not None and proc.stdout is not None
            proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            proc.stdin.close()
            line = proc.stdout.readline()
            if not line:
                stderr = proc.stderr.read() if proc.stderr else ""
                raise RuntimeError(f"MCP-сервер не вернул ответ: {stderr[:400]}")
            response = json.loads(line)
            if "error" in response:
                raise RuntimeError(f"MCP ошибка: {response['error']}")
            return response.get("result") or {}
        finally:
            try:
                proc.kill()
            except OSError:
                pass

    def initialize(self) -> dict[str, Any]:
        return self._request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "JARVIS", "version": "0.1.0"},
        })

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._request("tools/list")
        return list(result.get("tools") or [])

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        return self._request("tools/call", {"name": name, "arguments": arguments or {}})
