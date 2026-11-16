from unittest.mock import Mock

from crypto_analyst.coinglass_whales import CoinGlassWhaleClient


def test_coinglass_aggregates_positions_by_wallet_and_returns_top_200():
    session = Mock()
    response = Mock()
    response.json.return_value = {
        "code": "0",
        "data": [
            {"user": "0xA", "symbol": "BTC", "position_value_usd": 2_000_000,
             "unrealized_pnl": 100_000, "update_time": 100},
            {"user": "0xA", "symbol": "ETH", "position_value_usd": 1_000_000,
             "unrealized_pnl": -20_000, "update_time": 110},
            {"user": "0xB", "symbol": "BTC", "position_value_usd": 4_000_000,
             "unrealized_pnl": 50_000, "update_time": 120},
        ],
    }
    response.raise_for_status.return_value = None
    session.get.return_value = response
    client = CoinGlassWhaleClient(api_key="test-key", session=session)

    wallets = client.top_wallets(limit=200)

    assert [wallet.address for wallet in wallets] == ["0xB", "0xA"]
    assert wallets[1].position_count == 2
    assert wallets[1].gross_position_usd == 3_000_000
    assert wallets[1].unrealized_pnl_usd == 80_000
    assert wallets[1].symbols == ("BTC", "ETH")
    session.get.assert_called_once()
    assert session.get.call_args.kwargs["headers"]["CG-API-KEY"] == "test-key"


def test_coinglass_client_fails_closed_without_api_key():
    client = CoinGlassWhaleClient(api_key="")
    try:
        client.fetch_positions()
    except RuntimeError as exc:
        assert "COINGLASS_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected missing API key to fail")


def test_coinglass_rejects_invalid_limit():
    client = CoinGlassWhaleClient(api_key="test-key")
    try:
        client.top_wallets(limit=0)
    except ValueError as exc:
        assert "limit" in str(exc)
    else:
        raise AssertionError("Expected invalid limit to fail")
