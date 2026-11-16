"""Scheduled YouTube transcript ingestion and hypothesis extraction."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from typing import Any

from .hypothesis_extractor import TradingHypothesis, extract_hypothesis
from .youtube_monitor import YouTubeChannelMonitor, fetch_transcript_async

logger = logging.getLogger(__name__)


class YouTubeResearchService:
    def __init__(
        self,
        channel_ids: list[str],
        llm_generate: Callable[[str], str],
        journal: Any | None = None,
        poll_interval_seconds: int = 900,
        monitor: YouTubeChannelMonitor | None = None,
        transcript_fetcher: Callable[..., Any] | None = None,
    ):
        self.channel_ids = list(dict.fromkeys(
            channel.strip() for channel in channel_ids if channel.strip()
        ))
        if not self.channel_ids:
            raise ValueError("At least one YouTube channel ID is required.")
        if poll_interval_seconds < 60:
            raise ValueError("YouTube poll interval must be at least 60 seconds.")
        self.llm_generate = llm_generate
        self.journal = journal
        self.poll_interval_seconds = poll_interval_seconds
        self.monitor = monitor or YouTubeChannelMonitor()
        self.transcript_fetcher = transcript_fetcher or fetch_transcript_async
        self.processed_video_ids: set[str] = set()
        self.errors: list[str] = []

    async def scan_once(self) -> list[TradingHypothesis]:
        hypotheses = []
        for channel_id in self.channel_ids:
            try:
                videos = await self.monitor.fetch_latest_async(channel_id, limit=10)
            except Exception as exc:
                self.errors.append(f"Channel {channel_id}: {exc}")
                logger.warning("YouTube channel scan failed for %s: %s", channel_id, exc)
                continue
            for video in videos:
                if video.video_id in self.processed_video_ids:
                    continue
                self.processed_video_ids.add(video.video_id)
                try:
                    transcript = await self.transcript_fetcher(video.video_id)
                    from datetime import datetime, timezone
                    extracted_at = datetime.now(timezone.utc).isoformat()
                    hypothesis = await asyncio.to_thread(
                        extract_hypothesis, transcript, video.channel_id, video.video_id,
                        video.published_at, extracted_at, self.llm_generate,
                    )
                    hypotheses.append(hypothesis)
                    if self.journal:
                        await self.journal.record_hypothesis(hypothesis)
                except Exception as exc:
                    self.errors.append(f"Video {video.video_id}: {exc}")
                    logger.warning("YouTube transcript analysis failed for %s: %s", video.video_id, exc)
        return hypotheses

    async def run(self, stop_event: asyncio.Event,
                  on_hypothesis: Callable[[TradingHypothesis], Any] | None = None) -> None:
        while not stop_event.is_set():
            hypotheses = await self.scan_once()
            if on_hypothesis:
                for hypothesis in hypotheses:
                    result = on_hypothesis(hypothesis)
                    if inspect.isawaitable(result):
                        await result
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.poll_interval_seconds)
            except asyncio.TimeoutError:
                continue
