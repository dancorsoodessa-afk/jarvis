"""YouTube channel RSS monitoring and transcript collection."""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

import requests


YOUTUBE_RSS = "https://www.youtube.com/feeds/videos.xml"
ATOM = "{http://www.w3.org/2005/Atom}"
YT = "{http://www.youtube.com/xml/schemas/2015}"


@dataclass(frozen=True)
class YouTubeVideo:
    channel_id: str
    video_id: str
    title: str
    published_at: str
    video_url: str


class YouTubeChannelMonitor:
    def __init__(self, timeout: float = 10.0):
        self.timeout = max(2.0, min(30.0, float(timeout)))

    def fetch_latest(self, channel_id: str, limit: int = 15) -> list[YouTubeVideo]:
        channel_id = channel_id.strip()
        if not channel_id:
            raise ValueError("YouTube channel ID is required.")
        response = requests.get(
            YOUTUBE_RSS,
            params={"channel_id": channel_id},
            timeout=self.timeout,
            headers={"User-Agent": "JARVIS-Crypto-Research/1.0"},
        )
        response.raise_for_status()
        root = ET.fromstring(response.text)
        videos = []
        for entry in root.findall(f"{ATOM}entry")[:max(1, min(limit, 50))]:
            video_id = (entry.findtext(f"{YT}videoId") or "").strip()
            title = (entry.findtext(f"{ATOM}title") or "").strip()
            published = (entry.findtext(f"{ATOM}published") or "").strip()
            if not video_id:
                continue
            videos.append(YouTubeVideo(
                channel_id=channel_id,
                video_id=video_id,
                title=title,
                published_at=published,
                video_url=f"https://www.youtube.com/watch?v={video_id}",
            ))
        return videos

    async def fetch_latest_async(self, channel_id: str, limit: int = 15) -> list[YouTubeVideo]:
        return await asyncio.to_thread(self.fetch_latest, channel_id, limit)


def fetch_transcript(video_id: str, languages: tuple[str, ...] = ("ru", "en")) -> str:
    """Fetch available captions. Videos without accessible captions fail explicitly."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise RuntimeError(
            "Install youtube-transcript-api to collect video transcripts."
        ) from exc

    transcript = YouTubeTranscriptApi().fetch(video_id, languages=list(languages))
    parts = []
    for item in transcript:
        text = getattr(item, "text", None)
        if text:
            parts.append(str(text).replace("\\n", " ").strip())
    result = " ".join(part for part in parts if part)
    if not result:
        raise RuntimeError(f"No accessible transcript for YouTube video {video_id}.")
    return result


async def fetch_transcript_async(
    video_id: str,
    languages: tuple[str, ...] = ("ru", "en"),
) -> str:
    return await asyncio.to_thread(fetch_transcript, video_id, languages)
