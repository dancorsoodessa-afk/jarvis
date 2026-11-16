"""Public OKX instrument and liquidity discovery; REST is used only for universe refresh."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import requests


OKX_REST = "https://www.okx.com"


@dataclass(frozen=True)
class OKXInstrument:
    symbol: str
    market_type: str
    contract_multiplier: Decimal
    quote_volume_24h: Decimal


class OKXInstrumentDiscovery:
    def __init__(self, base_url: str = OKX_REST, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = max(2.0, min(30.0, float(timeout)))

    def _get_data(self, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
        response = requests.get(
            f"{self.base_url}{path}",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != "0":
            raise RuntimeError(f"OKX public API error: {payload.get('msg', 'unknown error')}")
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise RuntimeError("OKX public API response has no data list.")
        return [row for row in rows if isinstance(row, dict)]

    def fetch_instruments(self, market_type: str) -> list[dict[str, Any]]:
        mapping = {"spot": "SPOT", "swap": "SWAP"}
        inst_type = mapping.get(market_type.lower())
        if inst_type is None:
            raise ValueError("market_type must be 'spot' or 'swap'.")
        rows = self._get_data("/api/v5/public/instruments", {"instType": inst_type})
        result = []
        for row in rows:
            if row.get("state") != "live":
                continue
            if market_type.lower() == "spot" and row.get("quoteCcy") != "USDT":
                continue
            if market_type.lower() == "swap" and row.get("settleCcy") != "USDT":
                continue
            result.append(row)
        return result

    def fetch_tickers(self, market_type: str) -> list[dict[str, Any]]:
        mapping = {"spot": "SPOT", "swap": "SWAP"}
        inst_type = mapping.get(market_type.lower())
        if inst_type is None:
            raise ValueError("market_type must be 'spot' or 'swap'.")
        return self._get_data("/api/v5/market/tickers", {"instType": inst_type})

    def discover_liquid_instruments(
        self,
        include_spot: bool = True,
        include_swaps: bool = True,
        max_symbols: int = 500,
        min_quote_volume_usdt: Decimal = Decimal("250000"),
    ) -> list[OKXInstrument]:
        """Rank live USDT instruments by approximate 24h quote turnover.

        OKX reports spot volCcy24h in quote currency and derivatives volCcy24h
        in base currency. Derivative turnover is approximated as base volume * last.
        Linear USDT swaps are sized using ctVal * ctMult in base-currency units.
        """
        if not include_spot and not include_swaps:
            return []
        if max_symbols < 1:
            raise ValueError("max_symbols must be positive.")
        if min_quote_volume_usdt < 0:
            raise ValueError("min_quote_volume_usdt cannot be negative.")

        ranked: list[OKXInstrument] = []
        markets = []
        if include_spot:
            markets.append("spot")
        if include_swaps:
            markets.append("swap")

        for market_type in markets:
            instruments = self.fetch_instruments(market_type)
            allowed = {str(row.get("instId")): row for row in instruments if row.get("instId")}
            for ticker in self.fetch_tickers(market_type):
                symbol = str(ticker.get("instId") or "")
                instrument = allowed.get(symbol)
                if not instrument:
                    continue
                try:
                    volume = Decimal(str(ticker.get("volCcy24h", "0")))
                    last = Decimal(str(ticker.get("last", "0")))
                    if market_type == "swap":
                        volume *= last
                        contract_value = Decimal(str(instrument.get("ctVal", "0")))
                        contract_multiplier = Decimal(str(instrument.get("ctMult") or "1"))
                        base_currency = str(instrument.get("baseCcy") or "")
                        contract_currency = str(instrument.get("ctValCcy") or "")
                        if (
                            contract_value <= 0
                            or contract_multiplier <= 0
                            or not base_currency
                            or contract_currency != base_currency
                        ):
                            # Do not size a derivative when its contract unit is unknown.
                            continue
                        unit_multiplier = contract_value * contract_multiplier
                    else:
                        unit_multiplier = Decimal("1")
                except (InvalidOperation, TypeError, ValueError):
                    continue
                if (
                    not volume.is_finite()
                    or not last.is_finite()
                    or volume < min_quote_volume_usdt
                ):
                    continue
                ranked.append(OKXInstrument(
                    symbol=symbol,
                    market_type=market_type,
                    contract_multiplier=unit_multiplier,
                    quote_volume_24h=volume,
                ))

        ranked.sort(key=lambda item: item.quote_volume_24h, reverse=True)
        return ranked[:max_symbols]

    def discover_liquid_symbols(
        self,
        include_spot: bool = True,
        include_swaps: bool = True,
        max_symbols: int = 500,
        min_quote_volume_usdt: Decimal = Decimal("250000"),
    ) -> list[str]:
        return [
            item.symbol for item in self.discover_liquid_instruments(
                include_spot=include_spot,
                include_swaps=include_swaps,
                max_symbols=max_symbols,
                min_quote_volume_usdt=min_quote_volume_usdt,
            )
        ]

    def discover_usdt_symbols(self, include_spot: bool = True,
                              include_swaps: bool = True) -> list[str]:
        """Compatibility alias returning the liquid USDT universe."""
        return self.discover_liquid_symbols(
            include_spot=include_spot,
            include_swaps=include_swaps,
        )
