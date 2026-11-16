"""PostgreSQL journal for durable signals, paper orders, fills, positions, and research."""

from __future__ import annotations

import json
from typing import Any

from crypto_analyst.models import TradingSignal
from crypto_analyst.paper import PaperFill, PaperOrder
from strategic.hypothesis_extractor import TradingHypothesis


SCHEMA = """
CREATE TABLE IF NOT EXISTS crypto_signals (
    id BIGSERIAL PRIMARY KEY, symbol TEXT NOT NULL, side TEXT NOT NULL,
    entry NUMERIC NOT NULL, stop_loss NUMERIC NOT NULL, take_profit NUMERIC NOT NULL,
    imbalance NUMERIC NOT NULL, trade_delta NUMERIC NOT NULL, spread_bps NUMERIC NOT NULL,
    created_at_ms BIGINT NOT NULL, reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_orders (
    order_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, side TEXT NOT NULL,
    price NUMERIC NOT NULL, quantity NUMERIC NOT NULL, contract_multiplier NUMERIC NOT NULL,
    stop_loss NUMERIC NOT NULL, take_profit NUMERIC NOT NULL,
    filled_quantity NUMERIC NOT NULL, average_fill_price NUMERIC NOT NULL,
    fee_paid NUMERIC NOT NULL, status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_fills (
    id BIGSERIAL PRIMARY KEY, order_id TEXT NOT NULL, symbol TEXT NOT NULL,
    side TEXT NOT NULL, price NUMERIC NOT NULL, quantity NUMERIC NOT NULL,
    fee NUMERIC NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS paper_positions (
    position_id TEXT PRIMARY KEY, order_id TEXT NOT NULL, symbol TEXT NOT NULL,
    side TEXT NOT NULL, entry_price NUMERIC NOT NULL, exit_price NUMERIC NOT NULL,
    quantity NUMERIC NOT NULL, contract_multiplier NUMERIC NOT NULL,
    realized_pnl NUMERIC NOT NULL, status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trading_hypotheses (
    id BIGSERIAL PRIMARY KEY, asset TEXT NOT NULL, direction TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL, source_video TEXT NOT NULL,
    source_channel TEXT NOT NULL, published_at TEXT NOT NULL,
    extracted_at TEXT NOT NULL, payload JSONB NOT NULL
);
"""


class PostgresJournal:
    def __init__(self, dsn: str, pool: Any | None = None):
        if not dsn and pool is None:
            raise ValueError("PostgreSQL DSN is required.")
        self.dsn = dsn
        self.pool = pool

    async def connect(self) -> None:
        if self.pool is None:
            try:
                import asyncpg
            except ImportError as exc:
                raise RuntimeError("Install asyncpg to enable PostgreSQL persistence.") from exc
            self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5)
        await self.initialize()

    async def initialize(self) -> None:
        if self.pool is None:
            raise RuntimeError("PostgresJournal is not connected.")
        async with self.pool.acquire() as connection:
            await connection.execute(SCHEMA)

    async def record_signal(self, signal: TradingSignal) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute(
                """INSERT INTO crypto_signals
                (symbol, side, entry, stop_loss, take_profit, imbalance, trade_delta,
                 spread_bps, created_at_ms, reason)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
                signal.symbol, signal.side, signal.entry, signal.stop_loss,
                signal.take_profit, signal.imbalance, signal.trade_delta,
                signal.spread_bps, signal.created_at_ms, signal.reason,
            )

    async def record_order(self, order: PaperOrder) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute(
                """INSERT INTO paper_orders
                (order_id, symbol, side, price, quantity, contract_multiplier,
                 stop_loss, take_profit, filled_quantity, average_fill_price, fee_paid, status)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                ON CONFLICT (order_id) DO UPDATE SET
                status=EXCLUDED.status, filled_quantity=EXCLUDED.filled_quantity,
                average_fill_price=EXCLUDED.average_fill_price, fee_paid=EXCLUDED.fee_paid""",
                order.order_id, order.symbol, order.side, order.price, order.quantity,
                order.contract_multiplier, order.stop_loss, order.take_profit,
                order.filled_quantity, order.average_fill_price, order.fee_paid, order.status,
            )

    async def record_fill(self, fill: PaperFill) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute(
                """INSERT INTO paper_fills (order_id, symbol, side, price, quantity, fee)
                VALUES ($1,$2,$3,$4,$5,$6)""",
                fill.order_id, fill.symbol, fill.side, fill.price, fill.quantity, fill.fee,
            )

    async def record_position(self, position: Any) -> None:
        if position.status != "closed" or position.exit_price is None:
            return
        async with self.pool.acquire() as connection:
            await connection.execute(
                """INSERT INTO paper_positions
                (position_id, order_id, symbol, side, entry_price, exit_price,
                 quantity, contract_multiplier, realized_pnl, status)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT (position_id) DO NOTHING""",
                position.position_id, position.order_id, position.symbol, position.side,
                position.entry_price, position.exit_price, position.quantity,
                position.contract_multiplier, position.realized_pnl, position.status,
            )

    async def record_hypothesis(self, hypothesis: TradingHypothesis) -> None:
        payload = {
            "market": hypothesis.market,
            "entry_zone_low": hypothesis.entry_zone_low,
            "entry_zone_high": hypothesis.entry_zone_high,
            "invalidation_level": hypothesis.invalidation_level,
            "targets": list(hypothesis.targets),
            "timeframe": hypothesis.timeframe,
            "reasoning": hypothesis.reasoning,
        }
        async with self.pool.acquire() as connection:
            await connection.execute(
                """INSERT INTO trading_hypotheses
                (asset, direction, confidence, source_video, source_channel,
                 published_at, extracted_at, payload)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb)""",
                hypothesis.asset, hypothesis.direction, hypothesis.confidence,
                hypothesis.source_video, hypothesis.source_channel,
                hypothesis.published_at, hypothesis.extracted_at, json.dumps(payload),
            )

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None
