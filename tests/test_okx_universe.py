from decimal import Decimal
from unittest.mock import Mock, patch

from crypto_analyst.okx_universe import OKXInstrumentDiscovery


def response(rows):
    item = Mock()
    item.json.return_value = {"code": "0", "data": rows}
    item.raise_for_status.return_value = None
    return item


def test_liquid_universe_ranks_spot_quote_and_swap_base_turnover():
    spot_instruments = [
        {"instId": "BTC-USDT", "quoteCcy": "USDT", "state": "live"},
        {"instId": "ETH-USDT", "quoteCcy": "USDT", "state": "live"},
    ]
    spot_tickers = [
        {"instId": "BTC-USDT", "volCcy24h": "900000", "last": "100000"},
        {"instId": "ETH-USDT", "volCcy24h": "500000", "last": "3000"},
    ]
    swap_instruments = [
        {"instId": "BTC-USDT-SWAP", "settleCcy": "USDT", "state": "live"},
    ]
    swap_tickers = [
        {"instId": "BTC-USDT-SWAP", "volCcy24h": "20", "last": "100000"},
    ]
    with patch("crypto_analyst.okx_universe.requests.get", side_effect=[
        response(spot_instruments),
        response(spot_tickers),
        response(swap_instruments),
        response(swap_tickers),
    ]):
        symbols = OKXInstrumentDiscovery().discover_liquid_symbols(
            max_symbols=10,
            min_quote_volume_usdt=Decimal("250000"),
        )
    assert symbols == ["BTC-USDT-SWAP", "BTC-USDT", "ETH-USDT"]


def test_universe_rejects_zero_symbol_limit():
    try:
        OKXInstrumentDiscovery().discover_liquid_symbols(max_symbols=0)
    except ValueError as exc:
        assert "max_symbols" in str(exc)
    else:
        raise AssertionError("Expected invalid symbol limit to be rejected")
