"""Public spot market data connectors (Binance and Bybit)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    exchange: str
    price: float
    change_24h_pct: float
    quote_volume_24h: float
    candles: tuple[tuple[float, float, float, float, float, float], ...]
    observed_at: float
    source: str


class MarketDataError(RuntimeError):
    pass


class PublicMarketClient:
    """Fetch public spot prices and candles without API keys."""

    TIMEFRAMES = {"15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}

    def __init__(self, timeout: float = 8.0):
        self.timeout = max(3.0, min(float(timeout), 15.0))

    def _get_json(self, url: str) -> Any:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "JARVIS-Crypto/1.0", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise MarketDataError(f"Источник недоступен: {exc}") from exc

    @staticmethod
    def _symbol(symbol: str) -> str:
        value = "".join(ch for ch in str(symbol).upper() if ch.isalnum())
        if not value.endswith("USDT"):
            value += "USDT"
        if len(value) < 6 or len(value) > 24:
            raise ValueError("Некорректная торговая пара")
        return value

    def fetch_all(self, symbol: str = "BTCUSDT", timeframe: str = "1h", limit: int = 200) -> tuple[MarketSnapshot, ...]:
        pair = self._symbol(symbol)
        interval = self.TIMEFRAMES.get(timeframe)
        if not interval:
            raise ValueError("Неподдерживаемый таймфрейм")
        snapshots = []
        errors = []
        for exchange in ("Binance", "Bybit", "OKX"):
            try:
                if exchange == "Binance":
                    snapshots.append(self._binance(pair, interval, limit))
                elif exchange == "Bybit":
                    snapshots.append(self._bybit(pair, interval, limit))
                else:
                    snapshots.append(self._okx(pair, interval, limit))
            except (MarketDataError, ValueError, KeyError, TypeError) as exc:
                errors.append(f"{exchange}: {exc}")
        if not snapshots:
            raise MarketDataError(" | ".join(errors) or "Нет доступных источников")
        return tuple(snapshots)

    def fetch(self, symbol: str = "BTCUSDT", timeframe: str = "1h", limit: int = 200) -> MarketSnapshot:
        return self.fetch_all(symbol, timeframe, limit)[0]

    def _binance(self, pair: str, interval: str, limit: int) -> MarketSnapshot:
        root = "https://api.binance.com"
        encoded = urllib.parse.urlencode({"symbol": pair})
        ticker = self._get_json(f"{root}/api/v3/ticker/24hr?{encoded}")
        rows = self._get_json(
            f"{root}/api/v3/klines?{urllib.parse.urlencode({'symbol': pair, 'interval': interval, 'limit': min(max(int(limit), 30), 500)})}"
        )
        candles = tuple(
            (float(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]))
            for row in rows
        )
        price = float(ticker["lastPrice"])
        if not candles or price <= 0:
            raise MarketDataError("Биржа вернула пустые или некорректные данные")
        return MarketSnapshot(
            pair, "Binance", price, float(ticker["priceChangePercent"]),
            float(ticker["quoteVolume"]), candles, time.time(), "Binance Spot REST",
        )

    def _bybit(self, pair: str, interval: str, limit: int) -> MarketSnapshot:
        root = "https://api.bybit.com"
        query = urllib.parse.urlencode({"category": "spot", "symbol": pair})
        ticker_body = self._get_json(f"{root}/v5/market/tickers?{query}")
        items = ticker_body.get("result", {}).get("list", [])
        if not items:
            raise MarketDataError("Тикер не найден")
        ticker = items[0]
        interval_map = {"15m": "15", "1h": "60", "4h": "240", "1d": "D"}
        candle_query = urllib.parse.urlencode({
            "category": "spot", "symbol": pair, "interval": interval_map[interval],
            "limit": min(max(int(limit), 30), 200),
        })
        candle_body = self._get_json(f"{root}/v5/market/kline?{candle_query}")
        rows = candle_body.get("result", {}).get("list", [])
        candles = tuple(
            (float(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]))
            for row in reversed(rows)
        )
        price = float(ticker["lastPrice"])
        if not candles or price <= 0:
            raise MarketDataError("Биржа вернула пустые или некорректные данные")
        return MarketSnapshot(
            pair, "Bybit", price, float(ticker.get("price24hPcnt", 0.0)) * 100.0,
            float(ticker.get("turnover24h", 0.0)), candles, time.time(), "Bybit V5 Spot REST",
        )


    def _okx(self, pair: str, interval: str, limit: int) -> MarketSnapshot:
        root = "https://www.okx.com"
        base = pair[:-4]
        inst_id = f"{base}-USDT"
        ticker_body = self._get_json(
            f"{root}/api/v5/market/ticker?{urllib.parse.urlencode({'instId': inst_id})}"
        )
        items = ticker_body.get("data", [])
        if not items:
            raise MarketDataError("Тикер не найден")
        ticker = items[0]
        bar_map = {"15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"}
        candle_body = self._get_json(
            f"{root}/api/v5/market/candles?{urllib.parse.urlencode({'instId': inst_id, 'bar': bar_map[interval], 'limit': min(max(int(limit), 30), 300)})}"
        )
        rows = candle_body.get("data", [])
        candles = tuple(
            (float(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]))
            for row in reversed(rows)
        )
        price = float(ticker["last"])
        open_24h = float(ticker.get("open24h") or price)
        change = ((price / open_24h) - 1.0) * 100.0 if open_24h else 0.0
        if not candles or price <= 0:
            raise MarketDataError("Биржа вернула пустые или некорректные данные")
        return MarketSnapshot(
            pair, "OKX", price, change, float(ticker.get("volCcy24h") or 0.0),
            candles, time.time(), "OKX V5 Spot REST",
        )
