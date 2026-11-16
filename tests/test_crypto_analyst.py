from decimal import Decimal

import pytest

from crypto_analyst.config import CryptoConfig
from crypto_analyst.engine import ScalpingEngine
from crypto_analyst.models import Level, MarketTrade, OrderBookSnapshot, TradingSignal
from crypto_analyst.orderbook import bid_ask_imbalance, liquidity_walls, trade_delta
from crypto_analyst.paper import PaperBroker
from crypto_analyst.risk import RiskManager


def make_book(symbol="BTC-USDT-SWAP", received=10_000):
    return OrderBookSnapshot(
        symbol=symbol,
        bids=(
            Level(Decimal("100"), Decimal("100")),
            Level(Decimal("99.9"), Decimal("10")),
            Level(Decimal("99.8"), Decimal("10")),
        ),
        asks=(
            Level(Decimal("100.1"), Decimal("10")),
            Level(Decimal("100.2"), Decimal("10")),
            Level(Decimal("100.3"), Decimal("10")),
        ),
        timestamp_ms=received,
        received_at_ms=received,
    )


def test_crypto_config_rejects_live_trading():
    with pytest.raises(ValueError, match="paper-only"):
        CryptoConfig(paper_trading=False)
    with pytest.raises(ValueError, match="paper-only"):
        CryptoConfig(allow_live_orders=True)


def test_imbalance_and_walls_use_visible_book_levels():
    assert bid_ask_imbalance(make_book(), depth=3) > 0
    walls = liquidity_walls(make_book(), depth=3, multiple=Decimal("3"))
    assert walls["bids"] and walls["bids"][0]["price"] == Decimal("100")


def test_trade_delta_uses_aggressor_side():
    trades = [
        MarketTrade("BTC-USDT-SWAP", "buy", Decimal("100"), Decimal("3"), 10_000),
        MarketTrade("BTC-USDT-SWAP", "sell", Decimal("100"), Decimal("1"), 10_000),
    ]
    assert trade_delta(trades) == Decimal("2")


def test_engine_blocks_stale_and_non_whitelisted_symbols():
    engine = ScalpingEngine(whitelist={"ETH-USDT-SWAP"})
    assert engine.evaluate(make_book(), [], now_ms=10_001) is None
    engine = ScalpingEngine(whitelist={"BTC-USDT-SWAP"})
    assert engine.evaluate(make_book(received=1_000), [], now_ms=10_000) is None


def test_engine_requires_trade_confirmation():
    engine = ScalpingEngine(whitelist={"BTC-USDT-SWAP"})
    sells = [MarketTrade("BTC-USDT-SWAP", "sell", Decimal("100"), Decimal("5"), 10_000)]
    assert engine.evaluate(make_book(), sells, now_ms=10_000) is None


def test_risk_manager_approves_valid_paper_signal():
    signal = TradingSignal(
        "BTC-USDT-SWAP", "buy", Decimal("100"), Decimal("99"), Decimal("102"),
        Decimal("0.4"), Decimal("10"), Decimal("2"), 10_000, "test",
    )
    decision = RiskManager().approve(signal, Decimal("10000"), Decimal("0"), 0, 10_000, 10_000)
    assert decision.approved and decision.quantity > 0


def test_risk_manager_blocks_daily_loss_and_stale_data():
    signal = TradingSignal(
        "BTC-USDT-SWAP", "buy", Decimal("100"), Decimal("99"), Decimal("102"),
        Decimal("0.4"), Decimal("10"), Decimal("2"), 10_000, "test",
    )
    manager = RiskManager()
    assert not manager.approve(signal, Decimal("10000"), Decimal("-250"), 0, 10_000, 10_000).approved
    assert not manager.approve(signal, Decimal("10000"), Decimal("0"), 0, 20_000, 10_000).approved


def test_risk_manager_blocks_stop_too_close_to_estimated_liquidation():
    signal = TradingSignal(
        "BTC-USDT-SWAP", "buy", Decimal("100"), Decimal("50.2"), Decimal("200"),
        Decimal("0.4"), Decimal("10"), Decimal("2"), 10_000, "test",
    )
    decision = RiskManager().approve(
        signal, Decimal("10000"), Decimal("0"), 0, 10_000, 10_000,
        leverage=Decimal("2"),
    )
    assert not decision.approved
    assert "liquidation" in decision.reason.lower()


def test_paper_broker_fills_only_from_public_trade_events():
    signal = TradingSignal(
        "BTC-USDT-SWAP", "buy", Decimal("100"), Decimal("99"), Decimal("102"),
        Decimal("0.4"), Decimal("10"), Decimal("2"), 10_000, "test",
    )
    broker = PaperBroker(Decimal("1000"))
    order = broker.place_limit(signal, Decimal("2"))
    assert order.status == "open"
    assert broker.on_trade(MarketTrade(
        "BTC-USDT-SWAP", "buy", Decimal("100"), Decimal("5"), 10_001
    )) == []
    fills = broker.on_trade(MarketTrade(
        "BTC-USDT-SWAP", "sell", Decimal("99.9"), Decimal("1"), 10_002
    ))
    assert len(fills) == 1 and fills[0].quantity == Decimal("1")
    assert order.status == "partially_filled"


def test_paper_broker_has_no_live_order_method():
    broker = PaperBroker()
    assert broker.live_execution_enabled is False
    assert not hasattr(broker, "create_exchange_order")
