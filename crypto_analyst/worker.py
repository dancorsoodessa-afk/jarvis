"""Headless OKX paper-trading worker for VPS/container deployment."""

from __future__ import annotations

import asyncio
import os
import signal
import time
from decimal import Decimal

from .engine import ScalpingEngine
from .okx_universe import OKXInstrumentDiscovery
from .okx_ws import OKXPublicFeed
from .paper import PaperBroker
from .risk import RiskManager
from .runtime import PaperScalpingRuntime
from storage.postgres_journal import PostgresJournal
from storage.redis_market_cache import RedisMarketCache
from strategic.gemini_adapter import create_gemini_generator
from strategic.youtube_service import YouTubeResearchService


async def run_worker() -> None:
    max_symbols = max(1, min(500, int(os.getenv("JARVIS_CRYPTO_MAX_SYMBOLS", "500"))))
    min_volume = Decimal(os.getenv("JARVIS_CRYPTO_MIN_VOLUME_USDT", "250000"))
    starting_balance = Decimal(os.getenv("JARVIS_PAPER_BALANCE", "10000"))

    discovery = OKXInstrumentDiscovery()
    instruments = await asyncio.to_thread(
        discovery.discover_liquid_instruments,
        True,
        True,
        max_symbols,
        min_volume,
    )
    if not instruments:
        raise RuntimeError("OKX returned no eligible liquid USDT instruments.")

    symbols = [item.symbol for item in instruments]
    derivatives = {item.symbol for item in instruments if item.market_type == "swap"}
    multipliers = {item.symbol: item.contract_multiplier for item in instruments}
    broker = PaperBroker(starting_balance=starting_balance)
    runtime = PaperScalpingRuntime(
        engine=ScalpingEngine(whitelist=set(symbols)),
        risk_manager=RiskManager(),
        broker=broker,
        contract_multipliers=multipliers,
        derivative_symbols=derivatives,
    )

    redis_url = os.getenv("JARVIS_REDIS_URL", "").strip()
    database_url = os.getenv("JARVIS_DATABASE_URL", "").strip()
    cache = RedisMarketCache(redis_url) if redis_url else None
    journal = PostgresJournal(database_url) if database_url else None

    try:
        if cache:
            await cache.connect()
        if journal:
            await journal.connect()

        print(
            f"JARVIS Crypto Analyst started: {len(symbols)} instruments, "
            f"paper balance={starting_balance} USDT, live orders disabled."
        )
        recorded_positions: set[str] = set()

        async def handle_message(message: dict) -> None:
            received_at_ms = int(time.time() * 1000)
            previous_fill_count = len(broker.fills)
            previous_order_count = len(runtime.orders)
            signals = runtime.on_market_message(message, received_at_ms)

            if cache:
                await cache.append_event(message, received_at_ms)
                symbol = str((message.get("arg") or {}).get("instId") or "")
                book = runtime.state.orderbooks.get(symbol)
                if book is not None and (message.get("arg") or {}).get("channel") == "books5":
                    await cache.cache_orderbook(book)

            for signal in signals:
                print(
                    f"PAPER SIGNAL {signal.side.upper()} {signal.symbol} "
                    f"entry={signal.entry} SL={signal.stop_loss} TP={signal.take_profit}"
                )
                if journal:
                    await journal.record_signal(signal)

            for order in runtime.orders[previous_order_count:]:
                if journal:
                    await journal.record_order(order)

            for fill in broker.fills[previous_fill_count:]:
                order = broker.orders[fill.order_id]
                if journal:
                    await journal.record_fill(fill)
                    await journal.record_order(order)

            if journal:
                for position in broker.positions.values():
                    if position.status == "closed" and position.position_id not in recorded_positions:
                        await journal.record_position(position)
                        recorded_positions.add(position.position_id)

        feed = OKXPublicFeed(
            symbols,
            handle_message,
            derivative_symbols=derivatives,
        )
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for stop_signal in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(stop_signal, stop_event.set)
            except (NotImplementedError, RuntimeError):
                pass
        tasks = [asyncio.create_task(feed.run(stop_event))]
        channel_ids = [
            item.strip()
            for item in os.getenv("JARVIS_YOUTUBE_CHANNEL_IDS", "").split(",")
            if item.strip()
        ]
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        if channel_ids and gemini_key:
            generator = create_gemini_generator(
                api_key=gemini_key,
                model=os.getenv("JARVIS_STRATEGIC_MODEL") or None,
                timeout=30,
            )
            research = YouTubeResearchService(
                channel_ids=channel_ids,
                llm_generate=generator,
                journal=journal,
                poll_interval_seconds=max(
                    60, int(os.getenv("JARVIS_YOUTUBE_POLL_SECONDS", "900"))
                ),
            )

            def report_hypothesis(item):
                print(
                    f"YOUTUBE HYPOTHESIS {item.asset} {item.direction.upper()} "
                    f"confidence={item.confidence:.2f} source={item.source_video}"
                )

            tasks.append(asyncio.create_task(
                research.run(stop_event, on_hypothesis=report_hypothesis)
            ))
        elif channel_ids:
            print("YouTube research skipped: GEMINI_API_KEY is not configured.")

        try:
            await asyncio.gather(*tasks)
        finally:
            stop_event.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        if cache:
            await cache.close()
        if journal:
            await journal.close()


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        print("JARVIS Crypto Analyst stopped.")


if __name__ == "__main__":
    main()
