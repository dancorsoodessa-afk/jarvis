from decimal import Decimal
from unittest.mock import Mock

from crypto_analyst.whale_intel import WhaleIntelClient


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.last_headers = None

    def get(self, url, headers=None, timeout=None, params=None):
        self.last_headers = headers or {}
        response = Mock()
        response.json.return_value = self.payload
        response.raise_for_status.return_value = None
        return response


def test_coinglass_whale_positions_sort_by_value_and_keep_liquidation_context():
    session = FakeSession({"code": "0", "data": [
        {"user": "0x" + "1" * 40, "symbol": "ETH", "position_size": "-20",
         "position_value_usd": 2_000_000, "entry_price": 2000, "mark_price": 1900,
         "liq_price": 2500, "leverage": 5, "unrealized_pnl": -2000,
         "funding_fee": 10, "update_time": 1700000000000},
        {"user": "0x" + "2" * 40, "symbol": "BTC", "position_size": "10",
         "position_value_usd": 5_000_000, "entry_price": 90000, "mark_price": 91000,
         "liq_price": 70000, "leverage": 3, "unrealized_pnl": 10000,
         "funding_fee": -5, "update_time": 1700000000001},
    ]})
    client = WhaleIntelClient(coinglass_api_key="key", session=session)
    rows = client.fetch_coinglass_whale_positions()
    assert rows[0].coin == "BTC"
    assert rows[0].side == "LONG"
    assert rows[0].position_value_usd == Decimal("5000000")
    assert rows[1].side == "SHORT"
    assert rows[1].liquidation_price == Decimal("2500")
    assert session.last_headers["CG-API-KEY"] == "key"


def test_coinglass_alert_is_position_event_not_trade_fill():
    session = FakeSession({"code": "0", "data": [{
        "user": "0x" + "3" * 40, "symbol": "BTC", "position_size": "-12",
        "entry_price": 90000, "position_value_usd": 1_080_000,
        "position_action": 2, "create_time": 1700000000000, "liq_price": 100000,
    }]})
    client = WhaleIntelClient(coinglass_api_key="key", session=session)
    rows = client.fetch_coinglass_whale_alerts()
    assert rows[0].side == "SHORT"
    assert rows[0].size_usd == Decimal("1080000")
    assert rows[0].raw["position_action"] == 2


def test_coinglass_adapter_fails_closed_without_key():
    client = WhaleIntelClient(coinglass_api_key="")
    try:
        client.fetch_coinglass_whale_positions()
    except RuntimeError as exc:
        assert "COINGLASS_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected missing CoinGlass API key to fail closed")
