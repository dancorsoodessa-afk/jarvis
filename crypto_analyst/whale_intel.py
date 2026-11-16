"""Public whale intelligence adapters for Hyperliquid and CoinLobster.

No exchange credentials are used. Public endpoints are rate-limited and their
availability/refresh cadence is controlled by the providers.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from datetime import datetime, timedelta, timezone
import os
import time

import requests


HYPERLIQUID_LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"
COINLOBSTER_PUBLIC_URL = "https://coinlobster.com/api/public"


def _rows(payload: Any) -> list[dict[str, Any]]:
    """Accept the common list/envelope shapes used by public analytics APIs."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "rows", "items", "results", "trades", "accounts", "leaderboardRows"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _rows(value)
            if nested:
                return nested
    return []


def _number(value: Any) -> Decimal:
    try:
        result = Decimal(str(value if value is not None else "0"))
        return result if result.is_finite() else Decimal("0")
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


@dataclass(frozen=True)
class WhaleAccount:
    rank: int
    address: str
    name: str
    pnl_usd: Decimal
    roi: Decimal
    volume_usd: Decimal
    equity_usd: Decimal
    window: str = "month"


@dataclass(frozen=True)
class WhaleTrade:
    timestamp: str
    address: str
    coin: str
    side: str
    price: Decimal
    size_usd: Decimal
    venue: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class WhalePosition:
    address: str
    coin: str
    side: str
    position_value_usd: Decimal
    position_size: Decimal
    entry_price: Decimal
    mark_price: Decimal
    liquidation_price: Decimal
    leverage: Decimal
    unrealized_pnl_usd: Decimal
    funding_fee_usd: Decimal
    update_time: str
    raw: dict[str, Any]


class WhaleIntelClient:
    """Read-only whale data client. It has no exchange order methods."""

    def __init__(self, timeout: float = 12.0, session: requests.Session | None = None, nansen_api_key: str | None = None, coinglass_api_key: str | None = None):
        self.timeout = max(3.0, min(30.0, float(timeout)))
        self.session = session or requests.Session()
        session_headers = getattr(self.session, "headers", None)
        if hasattr(session_headers, "update"):
            session_headers.update({"User-Agent": "JARVIS-BOTok/1.0"})
        self.nansen_api_key = (nansen_api_key if nansen_api_key is not None else os.getenv("NANSEN_API_KEY", "")).strip()
        self.coinglass_api_key = (coinglass_api_key if coinglass_api_key is not None else os.getenv("COINGLASS_API_KEY", "")).strip()
        self.poll_interval_seconds = 60.0
        self._nansen_accounts_cache_at = 0.0
        self._nansen_trades_cache_at = 0.0
        self._nansen_accounts_cache: list[WhaleAccount] = []
        self._nansen_trades_cache: list[WhaleTrade] = []
        self._leaderboard_cache_at = 0.0
        self._leaderboard_cache: list[WhaleAccount] = []

    def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        request_timeout = max(self.timeout, 60.0) if url == HYPERLIQUID_LEADERBOARD_URL else self.timeout
        response = self.session.get(url, params=params, timeout=request_timeout)
        response.raise_for_status()
        return response.json()

    def fetch_top_hyperliquid_accounts(
        self, limit: int = 200, window: str = "month"
    ) -> list[WhaleAccount]:
        """Rank public Hyperliquid leaderboard accounts by PnL.

        Hyperliquid publishes fixed windows: day, week, month and allTime.
        This is a ranking of Hyperliquid accounts, not all crypto whales.
        """
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        if window not in {"day", "week", "month", "allTime"}:
            raise ValueError("unsupported Hyperliquid leaderboard window")
        now = time.monotonic()
        if self._leaderboard_cache and now - self._leaderboard_cache_at < 900:
            return self._leaderboard_cache[:limit]
        payload = self._get_json(HYPERLIQUID_LEADERBOARD_URL)
        source_rows = _rows(payload)
        ranked: list[WhaleAccount] = []
        for row in source_rows:
            address = str(row.get("ethAddress") or row.get("address") or "").strip()
            if not address:
                continue
            performances = row.get("windowPerformances") or {}
            metrics: Any = performances.get(window, {}) if isinstance(performances, dict) else {}
            if isinstance(performances, (list, tuple)):
                metrics = next((entry[1] for entry in performances if isinstance(entry, (list, tuple)) and len(entry) > 1 and entry[0] == window), {})
            if not isinstance(metrics, dict):
                metrics = {}
            ranked.append(WhaleAccount(
                rank=0,
                address=address,
                name=str(row.get("displayName") or row.get("name") or ""),
                pnl_usd=_number(metrics.get("pnl")),
                roi=_number(metrics.get("roi")),
                volume_usd=_number(metrics.get("vlm") or metrics.get("volume")),
                equity_usd=_number(row.get("accountValue") or row.get("equity")),
                window=window,
            ))
        ranked.sort(key=lambda item: item.pnl_usd, reverse=True)
        self._leaderboard_cache = [
            WhaleAccount(
                rank=index + 1, address=item.address, name=item.name,
                pnl_usd=item.pnl_usd, roi=item.roi, volume_usd=item.volume_usd,
                equity_usd=item.equity_usd, window=item.window,
            )
            for index, item in enumerate(ranked)
        ]
        self._leaderboard_cache_at = now
        return self._leaderboard_cache[:limit]

    def fetch_hyperliquid_whale_trades(self, limit: int = 200) -> list[WhaleTrade]:
        """Get wallet-attributed Hyperliquid whale fills from CoinLobster."""
        payload = self._get_json(
            f"{COINLOBSTER_PUBLIC_URL}/hyperliquid/whales",
            params={"limit": max(1, min(200, int(limit)))},
        )
        return self._normalize_trades(_rows(payload), venue="Hyperliquid")

    def fetch_exchange_whale_trades(self, limit: int = 100) -> list[WhaleTrade]:
        """Get the provider's public cross-exchange whale tape."""
        payload = self._get_json(
            f"{COINLOBSTER_PUBLIC_URL}/crypto-whales",
            params={"limit": max(1, min(200, int(limit)))},
        )
        return self._normalize_trades(_rows(payload), venue="multi-exchange")

    @staticmethod
    def _normalize_trades(rows: list[dict[str, Any]], venue: str) -> list[WhaleTrade]:
        result = []
        for row in rows:
            address = str(
                row.get("wallet") or row.get("address") or row.get("user")
                or row.get("account") or row.get("trader_address") or ""
            )
            coin = str(row.get("coin") or row.get("symbol") or row.get("token") or row.get("token_symbol") or "—")
            side = str(row.get("side") or row.get("direction") or "—").upper()
            timestamp = str(
                row.get("timestamp") or row.get("time") or row.get("ts")
                or row.get("created_at") or row.get("block_timestamp") or "—"
            )
            price = _number(row.get("price") or row.get("px") or row.get("price_usd"))
            size = _number(
                row.get("size_usd") or row.get("notional_usd")
                or row.get("usd_value") or row.get("value_usd")
            )
            if size == 0:
                size = _number(row.get("size") or row.get("sz")) * price
            result.append(WhaleTrade(
                timestamp=timestamp, address=address, coin=coin, side=side,
                price=price, size_usd=size,
                venue=str(row.get("venue") or row.get("exchange") or venue),
                raw=dict(row),
            ))
        return result

    def _get_coinglass(self, path: str) -> list[dict[str, Any]]:
        if not self.coinglass_api_key:
            raise RuntimeError("COINGLASS_API_KEY is not configured")
        response = self.session.get(
            f"https://open-api-v4.coinglass.com{path}",
            headers={"CG-API-KEY": self.coinglass_api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or str(payload.get("code")) != "0":
            message = payload.get("msg", "unknown CoinGlass API error") if isinstance(payload, dict) else "invalid response"
            raise RuntimeError(f"CoinGlass API error: {message}")
        return _rows(payload)

    def fetch_coinglass_whale_positions(self, limit: int = 200) -> list[WhalePosition]:
        """Fetch current Hyperliquid positions above the provider's $1M threshold."""
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        rows = self._get_coinglass("/api/hyperliquid/whale-position")
        positions = []
        for row in rows:
            size = _number(row.get("position_size"))
            positions.append(WhalePosition(
                address=str(row.get("user") or ""),
                coin=str(row.get("symbol") or "—"),
                side="LONG" if size > 0 else "SHORT" if size < 0 else "—",
                position_value_usd=_number(row.get("position_value_usd")),
                position_size=size,
                entry_price=_number(row.get("entry_price")),
                mark_price=_number(row.get("mark_price")),
                liquidation_price=_number(row.get("liq_price")),
                leverage=_number(row.get("leverage")),
                unrealized_pnl_usd=_number(row.get("unrealized_pnl")),
                funding_fee_usd=_number(row.get("funding_fee")),
                update_time=str(row.get("update_time") or "—"),
                raw=dict(row),
            ))
        positions.sort(key=lambda item: item.position_value_usd, reverse=True)
        return positions[:limit]

    def fetch_coinglass_whale_alerts(self, limit: int = 200) -> list[WhaleTrade]:
        """Fetch recent >$1M Hyperliquid position-open/close alerts.

        These are position tracking events, not individual buy/sell fills.
        """
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        rows = self._get_coinglass("/api/hyperliquid/whale-alert")
        result = []
        for row in rows[:limit]:
            size = _number(row.get("position_size"))
            result.append(WhaleTrade(
                timestamp=str(row.get("create_time") or "—"),
                address=str(row.get("user") or ""),
                coin=str(row.get("symbol") or "—"),
                side="LONG" if size > 0 else "SHORT" if size < 0 else "—",
                price=_number(row.get("entry_price")),
                size_usd=_number(row.get("position_value_usd")),
                venue="CoinGlass Hyperliquid position alert",
                raw=dict(row),
            ))
        return result

    def _post_nansen(self, endpoint: str, payload: dict[str, Any]) -> Any:
        if not self.nansen_api_key:
            raise RuntimeError("NANSEN_API_KEY is not configured")
        response = self.session.post(
            f"https://api.nansen.ai{endpoint}",
            json=payload,
            headers={"apikey": self.nansen_api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def fetch_nansen_top_traders(self, limit: int = 200) -> list[WhaleAccount]:
        """Fetch the top Hyperliquid perp traders for the trailing 30-day window."""
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=30)
        payload = self._post_nansen("/api/v1/perp-leaderboard", {
            "date": {"from": start.isoformat(), "to": end.isoformat()},
            "pagination": {"page": 1, "per_page": limit},
            "order_by": [{"field": "total_pnl", "direction": "DESC"}],
        })
        rows = _rows(payload)
        accounts = []
        for row in rows:
            address = str(row.get("trader_address") or row.get("address") or "")
            if not address:
                continue
            accounts.append(WhaleAccount(
                rank=len(accounts) + 1,
                address=address,
                name=str(row.get("trader_address_label") or ""),
                pnl_usd=_number(row.get("total_pnl")),
                roi=_number(row.get("roi")),
                volume_usd=_number(row.get("volume_usd")),
                equity_usd=_number(row.get("account_value")),
                window="30d",
            ))
        return accounts[:limit]

    def fetch_nansen_smart_money_trades(self, limit: int = 200) -> list[WhaleTrade]:
        """Fetch the latest Smart HL Perps Trader fills (seven-day maximum window)."""
        payload = self._post_nansen("/api/v1/smart-money/perp-trades", {
            "lookback_hours": 24,
            "pagination": {"page": 1, "per_page": max(1, min(1000, int(limit)))},
            "order_by": [{"field": "block_timestamp", "direction": "DESC"}],
        })
        return self._normalize_trades(_rows(payload), venue="Nansen Smart Money / Hyperliquid")

    def _cached_nansen_accounts(self, limit: int) -> list[WhaleAccount]:
        now = time.monotonic()
        if not self._nansen_accounts_cache or now - self._nansen_accounts_cache_at >= 300:
            self._nansen_accounts_cache = self.fetch_nansen_top_traders(limit)
            self._nansen_accounts_cache_at = now
        return self._nansen_accounts_cache[:limit]

    def _cached_nansen_trades(self, limit: int) -> list[WhaleTrade]:
        now = time.monotonic()
        if not self._nansen_trades_cache or now - self._nansen_trades_cache_at >= 60:
            self._nansen_trades_cache = self.fetch_nansen_smart_money_trades(limit)
            self._nansen_trades_cache_at = now
        return self._nansen_trades_cache[:limit]

    def fetch_snapshot(self, account_limit: int = 200) -> dict[str, Any]:
        """Return independent source results so one provider outage is non-fatal."""
        snapshot: dict[str, Any] = {
            "accounts": [], "hyperliquid_trades": [], "exchange_trades": [],
            "positions": [], "alerts": [], "errors": [],
            "source": "Hyperliquid public leaderboard + CoinLobster public API",
        }
        operations = []
        if self.nansen_api_key:
            snapshot["source"] = "Nansen Hyperliquid leaderboard + Smart Money trades"
            operations.extend((
                ("accounts", lambda: self._cached_nansen_accounts(account_limit)),
                ("hyperliquid_trades", lambda: self._cached_nansen_trades(200)),
            ))
        else:
            operations.extend((
                ("accounts", lambda: self.fetch_top_hyperliquid_accounts(account_limit)),
                ("hyperliquid_trades", lambda: self.fetch_hyperliquid_whale_trades(200)),
                ("exchange_trades", lambda: self.fetch_exchange_whale_trades(100)),
            ))
        if self.coinglass_api_key:
            snapshot["source"] += " + CoinGlass live Hyperliquid whale positions/alerts"
            operations.extend((
                ("positions", lambda: self.fetch_coinglass_whale_positions(200)),
                ("alerts", lambda: self.fetch_coinglass_whale_alerts(200)),
            ))
        for key, operation in operations:
            try:
                snapshot[key] = operation()
            except Exception as exc:
                snapshot["errors"].append(f"{key}: {type(exc).__name__}: {exc}")
        if self.nansen_api_key and (
            not snapshot["accounts"] or not snapshot["hyperliquid_trades"]
        ):
            fallback = (
                ("accounts", lambda: self.fetch_top_hyperliquid_accounts(account_limit)),
                ("hyperliquid_trades", lambda: self.fetch_hyperliquid_whale_trades(200)),
                ("exchange_trades", lambda: self.fetch_exchange_whale_trades(100)),
            )
            for key, operation in fallback:
                if snapshot.get(key):
                    continue
                try:
                    snapshot[key] = operation()
                except Exception as exc:
                    snapshot["errors"].append(f"public_{key}: {type(exc).__name__}: {exc}")
            snapshot["source"] += " · public fallback where Nansen was unavailable"
        return snapshot

    def fetch_account_state(self, address: str) -> dict[str, Any]:
        """Read current Hyperliquid positions for one public account."""
        if not address.startswith("0x") or len(address) != 42:
            raise ValueError("invalid Hyperliquid account address")
        response = self.session.post(
            HYPERLIQUID_INFO_URL,
            json={"type": "clearinghouseState", "user": address},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def fetch_account_fills(self, address: str) -> list[dict[str, Any]]:
        """Read recent public fills for one account; callers must throttle requests."""
        if not address.startswith("0x") or len(address) != 42:
            raise ValueError("invalid Hyperliquid account address")
        response = self.session.post(
            HYPERLIQUID_INFO_URL,
            json={"type": "userFills", "user": address},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return _rows(response.json())
