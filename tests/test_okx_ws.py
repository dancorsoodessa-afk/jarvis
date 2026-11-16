from crypto_analyst.okx_ws import OKXPublicFeed


def test_public_feed_shards_instruments_and_subscribes_to_three_channels():
    feed = OKXPublicFeed(
        [f"COIN{i}-USDT-SWAP" for i in range(65)],
        lambda _message: None,
        instruments_per_connection=30,
    )
    chunks = [
        feed.symbols[index:index + feed.instruments_per_connection]
        for index in range(0, len(feed.symbols), feed.instruments_per_connection)
    ]
    assert [len(chunk) for chunk in chunks] == [30, 30, 5]
    first = feed._subscriptions(chunks[0])
    assert len(first["args"]) == 90
    assert {item["channel"] for item in first["args"]} == {"books5", "trades", "tickers"}
