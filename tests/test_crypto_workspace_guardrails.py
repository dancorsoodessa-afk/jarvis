from crypto_analyst.config import CryptoConfig


def test_default_crypto_universe_is_bounded_and_paper_only():
    config = CryptoConfig()
    assert config.exchange == "okx"
    assert config.max_symbols == 500
    assert config.paper_trading is True
    assert config.allow_live_orders is False


def test_only_spot_and_swap_markets_are_enabled():
    assert CryptoConfig().market_types == ("spot", "swap")
