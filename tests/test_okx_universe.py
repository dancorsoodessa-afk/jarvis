from decimal import Decimal
from unittest.mock import Mock, patch

from crypto_analyst.okx_universe import OKXInstrumentDiscovery


def response(rows):
    item = Mock()
    item.json.return_value = {"code": "0", "data": rows}
    item.raise_for_status.return_value = None
    return item


def test_liquid_universe_ranks_spot_quote_and_swap_base_turnover():
    with patch("crypto_analyst.okx_universe.requests.get", side_effect=[
        response([
            {"instId": "BTC-USDT", "quoteCcy": "USDT", "state": "live"},
            {"instId": "ETH-USDT", "quoteCcy": "USDT", "state": "live"},
        ]),
        response([
            {"instId": "BTC-USDT", "volCcy24h": "900000", "last": "100000"},
            {"instId": "ETH-USDT", "volCcy24h": "500000", "last": "3000"},
        ]),
        response([{
            "instId": "BTC-USDT-SWAP", "settleCcy": "USDT", "state": "live",
            "baseCcy": "BTC", "ctVal": "0.01", "ctMult": "1", "ctValCcy": "BTC",
        }]),
        response([{"instId": "BTC-USDT-SWAP", "volCcy24h": "20", "last": "100000"}]),
    ]):
        symbols = OKXInstrumentDiscovery().discover_liquid_symbols(
            max_symbols=10, min_quote_volume_usdt=Decimal("250000")
        )
    assert symbols == ["BTC-USDT-SWAP", "BTC-USDT", "ETH-USDT"]


def test_universe_rejects_zero_symbol_limit():
    try:
        OKXInstrumentDiscovery().discover_liquid_symbols(max_symbols=0)
    except ValueError as exc:
        assert "max_symbols" in str(exc)
    else:
        raise AssertionError("Expected invalid symbol limit to be rejected")


def test_swap_contract_multiplier_uses_ctval_and_ctmult():
    with patch("crypto_analyst.okx_universe.requests.get", side_effect=[
        response([{
            "instId": "BTC-USDT-SWAP", "settleCcy": "USDT", "state": "live",
            "baseCcy": "BTC", "ctVal": "0.01", "ctMult": "2", "ctValCcy": "BTC",
        }]),
        response([{"instId": "BTC-USDT-SWAP", "volCcy24h": "20", "last": "100000"}]),
    ]):
        instruments = OKXInstrumentDiscovery().discover_liquid_instruments(
            include_spot=False, include_swaps=True, max_symbols=10,
            min_quote_volume_usdt=Decimal("100000"),
        )
    assert len(instruments) == 1
    assert instruments[0].contract_multiplier == Decimal("0.02")
