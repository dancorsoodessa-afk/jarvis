"""Crypto adaptation of the 11 Trader Skill workflows. Public data; paper-only orders."""
from __future__ import annotations
import json, time, urllib.parse, urllib.request, uuid
from pathlib import Path
from typing import Any

OKX_BASE = "https://www.okx.com"

def _get_json(url: str, timeout: int = 12) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-Crypto-Analyst/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))

def _okx_get(path: str, params: dict[str, str] | None = None) -> dict:
    query = urllib.parse.urlencode(params or {})
    data = _get_json(f"{OKX_BASE}{path}" + (f"?{query}" if query else ""))
    if data.get("code") != "0":
        raise RuntimeError(f"OKX API error: {data.get('msg', 'unknown error')}")
    return data

def _symbol(value: str) -> str:
    value = value.strip().upper().replace("/", "-")
    if not value: raise ValueError("Укажите торговую пару, например BTC-USDT")
    return value if "-" in value else f"{value}-USDT"

def _data_dir(path: str | None = None) -> Path:
    target = Path(path) if path else Path("data/crypto")
    target.mkdir(parents=True, exist_ok=True)
    return target

# 1. Copycat: monitor a public BTC address; this is not a full investor portfolio.
def trader_copycat(address: str) -> dict:
    address = address.strip()
    if not address: raise ValueError("Укажите публичный BTC-адрес")
    data = _get_json(f"https://blockstream.info/api/address/{urllib.parse.quote(address)}")
    stats = data.get("chain_stats", {})
    funded, spent = int(stats.get("funded_txo_sum", 0)), int(stats.get("spent_txo_sum", 0))
    return {"address": address, "asset": "BTC", "balance_sats": funded-spent,
            "balance_btc": (funded-spent)/100_000_000, "tx_count": int(stats.get("tx_count", 0)),
            "note": "Публичный баланс адреса; это не полный портфель владельца."}

# 2. News: public CoinDesk RSS feed, optionally filtered by tickers.
def trader_news(symbols: str = "") -> list[dict]:
    req = urllib.request.Request("https://www.coindesk.com/arc/outboundfeeds/rss/",
                                 headers={"User-Agent": "JARVIS-Crypto-Analyst/1.0"})
    with urllib.request.urlopen(req, timeout=12) as response:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(response.read())
    wanted = {x.strip().upper().replace("-USDT", "") for x in symbols.split(",") if x.strip()}
    result = []
    for item in root.findall(".//item")[:50]:
        title, desc = item.findtext("title", ""), item.findtext("description", "")
        if not wanted or any(x in (title+" "+desc).upper() for x in wanted):
            result.append({"title": title, "url": item.findtext("link", ""),
                           "published": item.findtext("pubDate", "")})
    return result

# 3. Budget manager.
def trader_budget(budget: float, cash_buffer_pct: float = 10, max_position_pct: float = 25) -> dict:
    budget, reserve_pct, cap_pct = map(float, (budget, cash_buffer_pct, max_position_pct))
    if budget <= 0 or not 0 <= reserve_pct < 100 or not 0 < cap_pct <= 100:
        raise ValueError("Некорректный бюджет или процентные ограничения")
    reserve = budget*reserve_pct/100
    return {"budget": budget, "cash_reserve": round(reserve, 2),
            "investable": round(budget-reserve, 2), "max_position": round(budget*cap_pct/100, 2),
            "paper_only": True}

# 4. Whale watch: public address balance, without identity inference.
def trader_whale_watch(address: str) -> dict:
    return trader_copycat(address)

# 5. Analyst: live ticker snapshot from public OKX market API.
def trader_analyst(symbol: str = "BTC-USDT") -> dict:
    pair = _symbol(symbol)
    row = _okx_get("/api/v5/market/ticker", {"instId": pair})["data"][0]
    last, opening = float(row["last"]), float(row["open24h"])
    return {"symbol": pair, "last": last, "open24h": opening,
            "change_24h_pct": round((last/opening-1)*100, 4) if opening else 0,
            "high_24h": float(row["high24h"]), "low_24h": float(row["low24h"]),
            "volume_24h": float(row["vol24h"]), "timestamp_ms": int(row["ts"])}

# 6. Screener: liquid USDT spot pairs ranked by absolute 24h move.
def trader_screener(limit: int = 20, min_volume: float = 0) -> list[dict]:
    limit = int(limit)
    if not 1 <= limit <= 100: raise ValueError("limit должен быть от 1 до 100")
    rows = _okx_get("/api/v5/market/tickers", {"instType": "SPOT"})["data"]
    result = []
    for row in rows:
        if not row["instId"].endswith("-USDT"): continue
        volume = float(row.get("volCcy24h") or 0)
        if volume < float(min_volume): continue
        opening, last = float(row.get("open24h") or 0), float(row.get("last") or 0)
        result.append({"symbol": row["instId"], "last": last,
                       "change_24h_pct": round((last/opening-1)*100, 4) if opening else 0,
                       "volume_24h": volume})
    return sorted(result, key=lambda x: abs(x["change_24h_pct"]), reverse=True)[:limit]

# 7. Risk: position sizing; leverage fixed at 1x.
def trader_risk(balance: float, entry: float, stop: float, risk_pct: float = 1) -> dict:
    balance, entry, stop, risk_pct = map(float, (balance, entry, stop, risk_pct))
    if min(balance, entry, stop, risk_pct) <= 0 or risk_pct > 5 or entry == stop:
        raise ValueError("Проверьте баланс, цены и риск (допустимо 0–5%)")
    risk_cash = balance*risk_pct/100
    qty = risk_cash/abs(entry-stop)
    return {"risk_cash": round(risk_cash, 8), "quantity": round(qty, 8),
            "notional": round(qty*entry, 8), "risk_pct": risk_pct, "leverage": 1, "paper_only": True}

# 8. Broker: writes a paper ticket to disk; intentionally has no live-order route.
def trader_broker(symbol: str, side: str, quantity: float, price: float,
                  store_dir: str | None = None) -> dict:
    pair, side = _symbol(symbol), side.strip().upper()
    quantity, price = float(quantity), float(price)
    if side not in {"BUY", "SELL"} or quantity <= 0 or price <= 0:
        raise ValueError("Допустимы BUY/SELL и положительные количество/цена")
    folder = _data_dir(store_dir)
    file = folder/"paper_orders.json"
    orders = json.loads(file.read_text("utf-8")) if file.exists() else []
    ticket = {"id": str(uuid.uuid4()), "symbol": pair, "side": side, "quantity": quantity,
              "price": price, "notional": round(quantity*price, 8),
              "status": "PAPER_PENDING", "created_at": int(time.time()*1000)}
    orders.append(ticket)
    file.write_text(json.dumps(orders, ensure_ascii=False, indent=2), encoding="utf-8")
    return ticket

# 9. FIFO cost basis and realised PnL calculator; not tax advice.
def trader_tax(lots_json: str, sell_quantity: float, sell_price: float) -> dict:
    lots = json.loads(lots_json)
    remaining, proceeds, cost = float(sell_quantity), 0.0, 0.0
    if remaining <= 0 or float(sell_price) <= 0: raise ValueError("Количество и цена продажи должны быть положительными")
    for lot in lots:
        take = min(float(lot["quantity"]), remaining)
        cost += take*float(lot["buy_price"]); proceeds += take*float(sell_price)
        lot["quantity"] = float(lot["quantity"])-take; remaining -= take
        if remaining <= 1e-12: break
    if remaining > 1e-9: raise ValueError("Недостаточно монет в учёте лотов")
    return {"matched_quantity": float(sell_quantity), "cost_basis": round(cost, 8),
            "proceeds": round(proceeds, 8), "realized_pnl": round(proceeds-cost, 8),
            "remaining_lots": lots, "method": "FIFO", "disclaimer": "Не является налоговой консультацией."}

# 10. Price alert evaluator; caller supplies the current market price.
def trader_alerts(symbol: str, current_price: float, above: float | None = None,
                  below: float | None = None) -> list[dict]:
    price = float(current_price)
    if price <= 0: raise ValueError("Текущая цена должна быть положительной")
    result = []
    if above is not None and price >= float(above):
        result.append({"symbol": _symbol(symbol), "condition": "ABOVE", "target": float(above), "price": price})
    if below is not None and price <= float(below):
        result.append({"symbol": _symbol(symbol), "condition": "BELOW", "target": float(below), "price": price})
    return result

# 11. Rebalancer: calculate target allocation deltas; never submits trades.
def trader_rebalance(holdings_json: str, total_value: float) -> list[dict]:
    holdings, total = json.loads(holdings_json), float(total_value)
    if total <= 0 or not holdings: raise ValueError("Нужны позиции и положительная стоимость портфеля")
    if abs(sum(float(x["target_pct"]) for x in holdings)-100) > 0.01:
        raise ValueError("Целевые доли должны суммироваться до 100%")
    result = []
    for item in holdings:
        current = float(item.get("current_value", 0))
        target = total*float(item["target_pct"])/100
        result.append({"asset": item["asset"], "target_value": round(target, 8),
                       "current_value": round(current, 8), "delta": round(target-current, 8),
                       "action": "BUY" if target>current else ("SELL" if target<current else "HOLD")})
    return result
