from crypto_analyst.market_structure import Candle, detect_fair_value_gaps, detect_structure_breaks


def candle(ts, open_, high, low, close):
    return Candle(ts, open_, high, low, close)


def test_detects_bullish_and_bearish_fair_value_gaps():
    candles = [
        candle(1, 10, 11, 9, 10), candle(2, 11, 12, 10, 11),
        candle(3, 13, 14, 12, 13), candle(4, 13, 14, 11, 12),
        candle(5, 8, 9, 7, 8),
    ]
    gaps = detect_fair_value_gaps(candles)
    assert gaps[0].direction == "bullish" and gaps[0].lower == 11
    assert gaps[1].direction == "bearish"


def test_structure_breaks_confirm_bos_then_choch():
    candles = [
        candle(1, 10, 11, 9, 10), candle(2, 11, 13, 10, 12),
        candle(3, 10, 11, 8, 9), candle(4, 9, 10, 7, 8),
        candle(5, 8, 9, 6, 7), candle(6, 9, 10, 8, 9),
        candle(7, 5, 6, 4, 5), candle(8, 6, 8, 5, 7),
        candle(9, 8, 10, 7, 9), candle(10, 10, 12, 8, 11),
        candle(11, 11, 14, 10, 13), candle(12, 13, 13.5, 11, 13),
        candle(13, 14, 16, 13, 15),
    ]
    breaks = detect_structure_breaks(candles, swing_window=1)
    assert any(item.direction == "bearish" and item.kind == "BOS" for item in breaks)
    assert any(item.direction == "bullish" and item.kind == "CHoCH" for item in breaks)
