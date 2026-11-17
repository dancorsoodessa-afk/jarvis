"""Optional Nansen MCP connector and deterministic smart-wallet ranking.

The connector discovers the server's current tool schema instead of assuming
vendor-specific tool names. It is read-only: this module has no exchange order
or wallet-signing capability.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests


NANSEN_MCP_URL = "https://mcp.nansen.ai/ra/mcp/"
MCP_PROTOCOL_VERSION = "2025-03-26"


@dataclass(frozen=True)
class WhaleWallet:
    address: str
    label: str = ""
    realized_pnl_usd: float = 0.0
    win_rate: float = 0.0
    net_flow_usd: float = 0.0
    trade_count: int = 0
    source: str = "nansen"
    score: float = 0.0


def rank_whale_wallets(rows: list[dict[str, Any]], limit: int = 200) -> list[WhaleWallet]:
    """Rank supplied wallet rows; missing metrics are treated as unknown/zero."""
    if limit < 1:
        raise ValueError("limit must be positive")
    ranked: list[WhaleWallet] = []
    for row in rows:
        address = str(row.get("address") or row.get("wallet_address") or row.get("wallet") or "").strip()
        if not address:
            continue
        pnl = _number(row.get("realized_pnl_usd", row.get("realized_pnl", row.get("pnl", 0))))
        win_rate = _number(row.get("win_rate", row.get("winrate", 0)))
        net_flow = _number(row.get("net_flow_usd", row.get("net_flow", 0)))
        trade_count = max(0, int(_number(row.get("trade_count", row.get("tx_count", 0)))))
        score = (
            max(-100.0, min(100.0, pnl / 100_000.0)) * 0.45
            + max(0.0, min(1.0, win_rate)) * 25.0
            + max(-100.0, min(100.0, net_flow / 250_000.0)) * 0.20
            + min(10.0, trade_count / 20.0)
        )
        ranked.append(WhaleWallet(
            address=address,
            label=str(row.get("label") or row.get("entity") or ""),
            realized_pnl_usd=pnl,
            win_rate=win_rate,
            net_flow_usd=net_flow,
            trade_count=trade_count,
            source=str(row.get("source") or "nansen"),
            score=score,
        ))
    ranked.sort(key=lambda item: (item.score, item.realized_pnl_usd), reverse=True)
    return ranked[:limit]


def _number(value: Any) -> float:
    try:
        result = float(value or 0)
        return result if result == result and abs(result) != float("inf") else 0.0
    except (TypeError, ValueError):
        return 0.0


class NansenMCPClient:
    """Small Streamable-HTTP MCP client for Nansen's official endpoint."""

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str = NANSEN_MCP_URL,
        timeout: float = 20.0,
        session: requests.Session | None = None,
    ):
        self.api_key = (api_key or os.getenv("NANSEN_API_KEY", "")).strip()
        self.endpoint = endpoint
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session_id: str | None = None
        self._request_id = 0
        self.initialized = False

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "NANSEN-API-KEY": self.api_key,
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        }
        if self.session_id:
            headers["MCP-Session-Id"] = self.session_id
        return headers

    @staticmethod
    def _decode_response(response: requests.Response) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "").lower()
        if "text/event-stream" not in content_type:
            payload = response.json()
            return payload if isinstance(payload, dict) else {"result": payload}
        last_data = None
        for line in response.text.splitlines():
            if line.startswith("data:"):
                raw = line[5:].strip()
                if raw:
                    last_data = raw
        if last_data is None:
            raise RuntimeError("Nansen MCP returned an empty event stream.")
        payload = json.loads(last_data)
        if not isinstance(payload, dict):
            raise RuntimeError("Nansen MCP returned an invalid JSON-RPC response.")
        return payload

    def _post(self, payload: dict[str, Any], expect_result: bool = True) -> dict[str, Any]:
        response = self.session.post(
            self.endpoint, json=payload, headers=self._headers(), timeout=self.timeout
        )
        response.raise_for_status()
        self.session_id = response.headers.get("MCP-Session-Id", self.session_id)
        if not expect_result or response.status_code == 202 or not response.content:
            return {}
        result = self._decode_response(response)
        if result.get("error"):
            raise RuntimeError(f"Nansen MCP error: {result['error']}")
        return result

    def initialize(self) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("NANSEN_API_KEY is not configured.")
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "JARVIS-BOTok", "version": "1.0.0"},
            },
        }
        result = self._post(payload)
        self._post({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }, expect_result=False)
        self.initialized = True
        return result.get("result", {})

    def list_tools(self) -> list[dict[str, Any]]:
        if not self.initialized:
            self.initialize()
        tools: list[dict[str, Any]] = []
        cursor = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            result = self._post({
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/list",
                "params": params,
            })
            body = result.get("result") or {}
            tools.extend(item for item in body.get("tools", []) if isinstance(item, dict))
            cursor = body.get("nextCursor")
            if not cursor:
                break
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.initialized:
            self.initialize()
        if not name.strip():
            raise ValueError("Tool name is required.")
        result = self._post({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        body = result.get("result") or {}
        if body.get("isError"):
            raise RuntimeError(f"Nansen tool failed: {body.get('content')}")
        return body

    def relevant_tools(self) -> list[dict[str, Any]]:
        terms = ("wallet", "smart money", "trader", "dex trade", "leaderboard", "netflow", "portfolio")
        return [
            tool for tool in self.list_tools()
            if any(term in str(tool.get("name", "")).lower()
                   or term in str(tool.get("description", "")).lower()
                   for term in terms)
        ]
