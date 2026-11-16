def test_headless_crypto_worker_and_optional_storage_modules_import():
    from crypto_analyst.worker import run_worker
    from storage.postgres_journal import PostgresJournal
    from storage.redis_market_cache import RedisMarketCache
    from strategic.gemini_adapter import create_gemini_generator
    from strategic.youtube_service import YouTubeResearchService

    assert callable(run_worker)
    assert PostgresJournal is not None
    assert RedisMarketCache is not None
    assert callable(create_gemini_generator)
    assert YouTubeResearchService is not None


def test_live_exchange_order_path_is_absent_from_paper_broker():
    from crypto_analyst.paper import PaperBroker

    broker = PaperBroker()
    assert broker.live_execution_enabled is False
    assert not hasattr(broker, "create_exchange_order")
