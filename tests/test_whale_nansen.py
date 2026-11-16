from decimal import Decimal

from crypto_analyst.whale_intel import WhaleIntelClient


def test_hyperliquid_public_leaderboard_list_window_shape_and_cache():
    client = WhaleIntelClient()
    calls = []
    client._get_json = lambda *args, **kwargs: calls.append(1) or {
        "leaderboardRows": [{
            "ethAddress": "0x" + "1" * 40,
            "displayName": "Trader",
            "accountValue": "100000",
            "windowPerformances": [
                ["day", {"pnl": "1", "roi": "0.01", "vlm": "10"}],
                ["month", {"pnl": "500", "roi": "0.2", "vlm": "10000"}],
            ],
        }]
    }
    first = client.fetch_top_hyperliquid_accounts()
    second = client.fetch_top_hyperliquid_accounts()
    assert first[0].pnl_usd == Decimal("500")
    assert first[0].roi == Decimal("0.2")
    assert second[0].address == first[0].address
    assert len(calls) == 1


def test_nansen_leaderboard_uses_documented_request_and_maps_roi_fraction():
    client = WhaleIntelClient(nansen_api_key="test-key")
    captured = {}

    def fake_post(endpoint, payload):
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        return {"data": [{
            "trader_address": "0x" + "2" * 40,
            "trader_address_label": "Smart Trader",
            "total_pnl": 12500,
            "roi": 0.25,
            "volume_usd": 50000,
            "account_value": 75000,
        }]}

    client._post_nansen = fake_post
    rows = client.fetch_nansen_top_traders(200)
    assert captured["endpoint"] == "/api/v1/perp-leaderboard"
    assert captured["payload"]["pagination"]["per_page"] == 200
    assert rows[0].name == "Smart Trader"
    assert rows[0].roi == Decimal("0.25")
    assert rows[0].pnl_usd == Decimal("12500")


def test_nansen_smart_money_trade_maps_wallet_symbol_and_notional():
    client = WhaleIntelClient(nansen_api_key="test-key")
    client._post_nansen = lambda *args, **kwargs: {"data": [{
        "trader_address": "0x" + "3" * 40,
        "token_symbol": "BTC",
        "side": "Long",
        "action": "Buy - Open Long",
        "price_usd": 90000,
        "value_usd": 500000,
        "block_timestamp": "2026-11-16T20:00:00Z",
    }]}
    rows = client.fetch_nansen_smart_money_trades()
    assert rows[0].address.startswith("0x")
    assert rows[0].coin == "BTC"
    assert rows[0].size_usd == Decimal("500000")
    assert rows[0].side == "LONG"
