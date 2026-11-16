import asyncio
import json

from strategic.youtube_monitor import YouTubeVideo
from strategic.youtube_service import YouTubeResearchService


class FakeMonitor:
    async def fetch_latest_async(self, channel_id, limit=10):
        return [YouTubeVideo(
            channel_id, "video-1", "BTC analysis",
            "2026-11-16T10:00:00Z", "https://youtube.com/watch?v=video-1",
        )]


class FakeJournal:
    def __init__(self):
        self.hypotheses = []

    async def record_hypothesis(self, hypothesis):
        self.hypotheses.append(hypothesis)


def test_youtube_service_deduplicates_and_persists_hypotheses():
    async def scenario():
        journal = FakeJournal()
        response = json.dumps({
            "asset": "BTC-USDT", "market": "futures", "direction": "long",
            "entry_zone_low": 90000, "entry_zone_high": 91000,
            "invalidation_level": 89000, "targets": [93000],
            "timeframe": "4h", "confidence": 0.65,
            "reasoning": "Example source analysis",
        })

        async def transcript(_video_id):
            return "The author discusses a hypothetical BTC long setup."

        service = YouTubeResearchService(
            ["channel-1"], lambda _prompt: response, journal=journal,
            monitor=FakeMonitor(), transcript_fetcher=transcript,
        )
        first = await service.scan_once()
        second = await service.scan_once()
        assert len(first) == 1 and second == []
        assert len(journal.hypotheses) == 1
        assert first[0].source_video == "video-1"
    asyncio.run(scenario())
