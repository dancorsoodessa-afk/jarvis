from decimal import Decimal
from unittest.mock import Mock

import pytest

from crypto_analyst.whale_intel import WhaleIntelClient, _rows


def test_leaderboard_parser_ranks_accounts_by_month_pnl():
    client = WhaleIntelClient()
    client._get_json = lambda *args, **kwargs: {
        "leaderboardRows": [
            {"ethAddress": "0x" + "1" * 40, "displayName": "A",
             "accountValue": "1000", "windowPerformances": {"month": {"pnl": "50", "roi": "5", "vlm": "100"}}},
            {"ethAddress": "0x" + "2" * 40, "displayName": "B",
             "accountValue": "2000", "windowPerformances": {"month": {"pnl": "90", "roi": "9", "vlm": "200"}}},
        ]
    }
    rows = client.fetch_top_hyperliquid_accounts(200, "month")
    assert rows[0].name == "B"
    assert rows[0].rank == 1
    assert rows[0].pnl_usd == Decimal("90")


def test_leaderboard_rejects_invalid_limit_and_window():
    client = WhaleIntelClient()
    with pytest.raises(ValueError):
        client.fetch_top_hyperliquid_accounts(201)
    with pytest.raises(ValueError):
        client.fetch_top_hyperliquid_accounts(20, "quarter")


def test_coinlobster_trade_rows_keep_wallet_and_notional():
    rows = WhaleIntelClient._normalize_trades([{
        "wallet": "0x" + "a" * 40, "coin": "BTC", "side": "buy",
        "price": "100000", "size_usd": "2500000", "timestamp": "2026-11-16T20:00:00Z",
    }], "Hyperliquid")
    assert rows[0].address.startswith("0x")
    assert rows[0].size_usd == Decimal("2500000")
    assert rows[0].side == "BUY"


def test_envelope_parser_handles_list_and_data():
    assert len(_rows([{"a": 1}])) == 1
    assert len(_rows({"data": [{"a": 1}]})) == 1
