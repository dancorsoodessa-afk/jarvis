import 'dart:math' as math;

import 'okx_market.dart';
import 'signal_engine.dart';

typedef MarketCandleLoader = Future<List<MarketCandle>> Function(
  String instrumentId,
  String timeframe,
  int limit,
);

class MarketOpportunity {
  const MarketOpportunity({
    required this.instrument,
    required this.analysis,
    required this.price,
    required this.score,
  });

  final MarketInstrument instrument;
  final MultiTimeframeAnalysis analysis;
  final double price;
  final double score;
}

class MarketOpportunityScanner {
  const MarketOpportunityScanner({
    this.maxCandidates = 24,
    this.minimumTurnover = 100000,
    this.maximumSpreadPercent = 0.20,
  });

  final int maxCandidates;
  final double minimumTurnover;
  final double maximumSpreadPercent;

  Future<MarketOpportunity?> scan({
    required List<MarketInstrument> instruments,
    required String marketType,
    required MarketCandleLoader loadCandles,
  }) async {
    final kind = marketType == 'SPOT' ? 'SPOT' : 'SWAP';
    final eligible = instruments.where((item) {
      if (item.type != kind ||
          item.quote != 'USDT' ||
          item.state != 'live' ||
          item.turnover < minimumTurnover ||
          item.spreadPercent > maximumSpreadPercent ||
          item.lotSize <= 0 ||
          item.minSize <= 0) {
        return false;
      }
      if (kind == 'SWAP') {
        return item.contractSize > 0 && item.contractType == 'linear';
      }
      return item.contractSize == 0;
    }).toList()
      ..sort((a, b) => b.turnover.compareTo(a.turnover));

    MarketOpportunity? best;
    for (final instrument in eligible.take(maxCandidates)) {
      try {
        final loaded = await Future.wait([
          loadCandles(instrument.id, '5m', 120),
          loadCandles(instrument.id, '15m', 120),
          loadCandles(instrument.id, '1H', 120),
        ]);
        const timeframes = ['5m', '15m', '1H'];
        final byTimeframe = <String, List<MarketCandle>>{};
        for (var index = 0; index < timeframes.length; index++) {
          final closed = loaded[index].where((candle) => candle.isClosed).toList()
            ..sort((a, b) => a.timestamp.compareTo(b.timestamp));
          if (closed.length < 25 || closed.last.close <= 0) {
            byTimeframe.clear();
            break;
          }
          byTimeframe[timeframes[index]] = closed;
        }
        if (byTimeframe.length != timeframes.length) continue;

        final analysis = calculateMultiTimeframeAnalysis(
          pricesByTimeframe: byTimeframe.map(
            (timeframe, candles) => MapEntry(
              timeframe,
              candles.map((candle) => candle.close).toList(),
            ),
          ),
          candlesByTimeframe: byTimeframe,
        );
        if (!analysis.isAligned ||
            analysis.recommendation == 'ЖДАТЬ' ||
            (kind == 'SPOT' && analysis.signal.direction == 'SHORT')) {
          continue;
        }

        final price = byTimeframe['5m']!.last.close;
        final liquidityScore = math.log(instrument.turnover + 1);
        final score = analysis.signal.confidence * 0.55 +
            analysis.agreementPercent * 0.40 +
            liquidityScore * 0.05 -
            instrument.spreadPercent * 20;
        final candidate = MarketOpportunity(
          instrument: instrument,
          analysis: analysis,
          price: price,
          score: score,
        );
        if (best == null || candidate.score > best.score) best = candidate;
      } catch (_) {
        // One unavailable instrument must not abort the market-wide scan.
      }
    }
    return best;
  }
}
