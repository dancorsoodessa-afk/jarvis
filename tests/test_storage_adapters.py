import asyncio
from decimal import Decimal

from crypto_analyst.models import Level, OrderBookSnapshot, TradingSignal
from crypto_analyst.paper import PaperOrder, PaperPosition
from storage.postgres_journal import PostgresJournal
from storage.redis_market_cache import RedisMarketCache


class FakeRedis:
    def __init__(self):
        self.values, self.streams = {}, []

    async def ping(self):
        return True

    async def set(self, key, value, ex=None):
        self.values[key] = (value, ex)

    async def xadd(self, key, fields, maxlen=None, approximate=None):
        self.streams.append((key, fields, maxlen, approximate))
        return "1-0"

    async def xrange(self, key, min="-", max="+", count=None):
        return [("1-0", {
            "received_at_ms": "10001",
            "payload": '{"arg":{"channel":"books5","instId":"BTC-USDT"},"data":[]}',
        })]


class FakeConnection:
    def __init__(self):
        self.calls = []

    async def execute(self, query, *args):
        self.calls.append((query, args))


class FakeAcquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_args):
        return False


class FakePool:
    def __init__(self):
        self.connection = FakeConnection()

    def acquire(self):
        return FakeAcquire(self.connection)

    async def close(self):
        return None


def test_redis_cache_and_replay_event_stream():
    async def scenario():
        client = FakeRedis()
        cache = RedisMarketCache("redis://unused", client=client)
        await cache.connect()
        book = OrderBookSnapshot(
            "BTC-USDT",
            (Level(Decimal("100"), Decimal("2")),),
            (Level(Decimal("101"), Decimal("3")),),
            10_000, 10_001,
        )
        await cache.cache_orderbook(book)
        await cache.append_event({"arg": {"channel": "books5", "instId": "BTC-USDT"}, "data": []}, 10_001)
        events = await cache.read_events()
        assert "jarvis:crypto:book:BTC-USDT" in client.values
        assert events[0]["received_at_ms"] == 10001
        await cache.close()
    asyncio.run(scenario())


def test_postgres_journal_records_signals_orders_and_positions():
    async def scenario():
        pool = FakePool()
        journal = PostgresJournal("postgresql://unused", pool=pool)
        await journal.initialize()
        signal = TradingSignal(
            "BTC-USDT", "buy", Decimal("100"), Decimal("99"),
            Decimal("102"), Decimal("0.4"), Decimal("5"), Decimal("2"), 10_000, "test",
        )
        await journal.record_signal(signal)
        order = PaperOrder(
            "order-1", "BTC-USDT", "buy", Decimal("100"), Decimal("1"),
            Decimal("99"), Decimal("102"),
        )
        await journal.record_order(order)
        position = PaperPosition(
            "position-1", "order-1", "BTC-USDT", "buy",
            Decimal("100"), Decimal("1"), Decimal("99"), Decimal("102"),
            Decimal("1"), Decimal("0"), status="closed",
            exit_price=Decimal("101"), realized_pnl=Decimal("1"),
        )
        await journal.record_position(position)
        assert len(pool.connection.calls) == 4
        assert "CREATE TABLE IF NOT EXISTS crypto_signals" in pool.connection.calls[0][0]
        assert pool.connection.calls[1][1][0] == "BTC-USDT"
        assert "paper_orders" in pool.connection.calls[2][0]
        assert "paper_positions" in pool.connection.calls[3][0]
    asyncio.run(scenario())
