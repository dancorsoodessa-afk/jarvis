from crypto_analyst.market_state import MarketState
from crypto_analyst.okx_ws import OKXPublicFeed


def test_derivative_subscriptions_include_open_interest_funding_and_liquidations():
    payload = OKXPublicFeed._subscriptions(
        ("BTC-USDT-SWAP", "ETH-USDT"),
        derivative_symbols={"BTC-USDT-SWAP"},
        include_liquidations=True,
    )
    args = payload["args"]
    assert {"channel": "open-interest", "instId": "BTC-USDT-SWAP"} in args
    assert {"channel": "funding-rate", "instId": "BTC-USDT-SWAP"} in args
    assert {"channel": "liquidation-orders", "instType": "SWAP"} in args
    assert not any(
        item.get("channel") == "funding-rate" and item.get("instId") == "ETH-USDT"
        for item in args
    )


def test_market_state_stores_open_interest_funding_and_global_liquidations():
    state = MarketState()
    state.on_okx_message({
        "arg": {"channel": "open-interest", "instId": "BTC-USDT-SWAP"},
        "data": [{"oi": "100", "oiUsd": "1000000", "ts": "1700000000000"}],
    }, 1_700_000_000_001)
    state.on_okx_message({
        "arg": {"channel": "funding-rate", "instId": "BTC-USDT-SWAP"},
        "data": [{"fundingRate": "0.0001", "fundingTime": "1700000000000", "ts": "1700000000000"}],
    }, 1_700_000_000_002)
    state.on_okx_message({
        "arg": {"channel": "liquidation-orders", "instType": "SWAP"},
        "data": [{
            "instId": "BTC-USDT-SWAP",
            "details": [{"side": "sell", "posSide": "long", "sz": "3", "ts": "1700000000003"}],
        }],
    }, 1_700_000_000_003)
    assert state.open_interest["BTC-USDT-SWAP"]["oi"] == "100"
    assert state.funding_rates["BTC-USDT-SWAP"]["fundingRate"] == "0.0001"
    assert state.liquidations[-1]["symbol"] == "BTC-USDT-SWAP"
