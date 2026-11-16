import json

import pytest

from strategic.hypothesis_extractor import extract_hypothesis, validate_hypothesis


def test_hypothesis_validation_preserves_source_and_levels():
    item = validate_hypothesis({
        "asset": "btc-usdt",
        "market": "futures",
        "direction": "long",
        "entry_zone_low": 95000,
        "entry_zone_high": 96000,
        "invalidation_level": 94000,
        "targets": [97000, 98000],
        "timeframe": "4h",
        "confidence": 0.7,
        "reasoning": "Demand zone retest",
    }, "channel-1", "video-1", "2026-11-16", "2026-11-16T10:00:00Z")

    assert item.asset == "BTC-USDT"
    assert item.direction == "long"
    assert item.source_video == "video-1"
    assert item.targets == (97000.0, 98000.0)


def test_hypothesis_rejects_invalid_direction_and_confidence():
    with pytest.raises(ValueError, match="direction"):
        validate_hypothesis({"asset": "BTC", "direction": "moon"}, "c", "v", "", "")
    with pytest.raises(ValueError, match="Confidence"):
        validate_hypothesis({
            "asset": "BTC", "direction": "long", "confidence": 1.5
        }, "c", "v", "", "")


def test_extractor_calls_llm_only_with_transcript_and_validates_json():
    response = json.dumps({
        "asset": "ETH-USDT",
        "market": "both",
        "direction": "neutral",
        "entry_zone_low": None,
        "entry_zone_high": None,
        "invalidation_level": None,
        "targets": [],
        "timeframe": "1d",
        "confidence": 0,
        "reasoning": "No actionable setup",
    })
    seen = []
    result = extract_hypothesis(
        "Author discusses ETH but gives no trade setup.",
        "channel", "video", "published", "extracted",
        lambda prompt: seen.append(prompt) or response,
    )
    assert result.asset == "ETH-USDT"
    assert len(seen) == 1
    assert "ТРАНСКРИПТ" in seen[0]


def test_extractor_rejects_non_json_llm_response():
    with pytest.raises(ValueError, match="valid JSON"):
        extract_hypothesis("text", "c", "v", "", "", lambda _prompt: "not json")
