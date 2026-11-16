"""Public OKX instrument discovery; REST is used only for periodic universe refresh."""

from __future__ import annotations

from typing import Any

import requests


OKX_REST = "https://www.okx.com"


class OKXInstrumentDiscovery:
    def __init__(self, base_url: str = OKX_REST, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = max(2.0, min(30.0, float(timeout)))

    def fetch_instruments(self, market_type: str) -> list[dict[str, Any]]:
        mapping = {"spot": "SPOT", "swap": "SWAP"}
        inst_type = mapping.get(market_type.lower())
        if inst_type is None:
            raise ValueError("market_type must be 'spot' or 'swap'.")
        response = requests.get(
            f"{self.base_url}/api/v5/public/instruments",
            params={"instType": inst_type},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != "0":
            raise RuntimeError(f"OKX instruments error: {payload.get('msg', 'unknown error')}")
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise RuntimeError("OKX instruments response has no data list.")

        result = []
        for row in rows:
            if not isinstance(row, dict) or row.get("state") != "live":
                continue
            if market_type.lower() == "spot":
                if row.get("quoteCcy") != "USDT":
                    continue
            elif row.get("settleCcy") != "USDT":
                continue
            result.append(row)
        return result

    def discover_usdt_symbols(self, include_spot: bool = True,
                              include_swaps: bool = True) -> list[str]:
        if not include_spot and not include_swaps:
            return []
        symbols: list[str] = []
        if include_spot:
            symbols.extend(row["instId"] for row in self.fetch_instruments("spot"))
        if include_swaps:
            symbols.extend(row["instId"] for row in self.fetch_instruments("swap"))
        # Stable de-duplication while preserving OKX's returned ordering.
        return list(dict.fromkeys(symbols))
