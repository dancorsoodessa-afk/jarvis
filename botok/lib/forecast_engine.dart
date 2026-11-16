import 'dart:math' as math;

import 'okx_market.dart';

class MarketTimeframe {
  const MarketTimeframe(this.bar, this.label);
  final String bar;
  final String label;

  static const all = <MarketTimeframe>[
    MarketTimeframe('1m', '1 мин'),
    MarketTimeframe('3m', '3 мин'),
    MarketTimeframe('5m', '5 мин'),
    MarketTimeframe('15m', '15 мин'),
    MarketTimeframe('1H', '1 час'),
    MarketTimeframe('1D', '1 день'),
    MarketTimeframe('1W', '1 неделя'),
  ];
}

class ForecastPoint {
  const ForecastPoint(this.step, this.median, this.lower, this.upper);
  final int step;
  final double median;
  final double lower;
  final double upper;
}

class MarketForecast {
  const MarketForecast({
    required this.currentPrice,
    required this.bullishProbability,
    required this.bearishProbability,
    required this.points,
    required this.volatilityPercent,
  });

  final double currentPrice;
  final double bullishProbability;
  final double bearishProbability;
  final double volatilityPercent;
  final List<ForecastPoint> points;

  double get projectedMedian =>
      points.isEmpty ? currentPrice : points.last.median;
  double get projectedLower =>
      points.isEmpty ? currentPrice : points.last.lower;
  double get projectedUpper =>
      points.isEmpty ? currentPrice : points.last.upper;
}

class ForecastValidation {
  const ForecastValidation({
    required this.samples,
    required this.directionalAccuracyPercent,
    required this.intervalCoveragePercent,
    required this.meanAbsoluteErrorPercent,
  });

  final int samples;
  final double directionalAccuracyPercent;
  final double intervalCoveragePercent;
  final double meanAbsoluteErrorPercent;
}

double _normalCdf(double value) {
  final x = value.abs();
  final t = 1 / (1 + 0.2316419 * x);
  final density = 0.3989422804014327 * math.exp(-0.5 * x * x);
  final tail = density *
      t *
      (0.319381530 +
          t *
              (-0.356563782 +
                  t *
                      (1.781477937 +
                          t * (-1.821255978 + t * 1.330274429))));
  final positive = 1 - tail;
  return value >= 0 ? positive : 1 - positive;
}

MarketForecast? buildMarketForecast(
  List<MarketCandle> candles, {
  int horizonBars = 12,
}) {
  if (candles.length < 25 || horizonBars < 1) return null;
  final sorted = candles.toList()
    ..sort((a, b) => a.timestamp.compareTo(b.timestamp));
  final closes = sorted
      .map((c) => c.close)
      .where((v) => v > 0 && v.isFinite)
      .toList();
  if (closes.length < 25) return null;

  final returns = <double>[];
  for (var i = 1; i < closes.length; i++) {
    returns.add(math.log(closes[i] / closes[i - 1]));
  }
  final sample = returns.skip(math.max(0, returns.length - 60)).toList();
  if (sample.length < 20) return null;

  final rawMean = sample.reduce((a, b) => a + b) / sample.length;
  final variance = sample.fold<double>(
        0,
        (sum, value) => sum + math.pow(value - rawMean, 2).toDouble(),
      ) /
      math.max(1, sample.length - 1);
  final sigma = math.sqrt(variance);
  final shrinkage = sample.length / (sample.length + 30.0);
  final mean = rawMean * shrinkage;
  final current = closes.last;
  final horizonSigma = sigma * math.sqrt(horizonBars.toDouble());
  final z = horizonSigma < 1e-12
      ? 0.0
      : mean * horizonBars / horizonSigma;
  final bullish = (_normalCdf(z) * 100).clamp(1.0, 99.0).toDouble();

  final points = <ForecastPoint>[];
  for (var step = 1; step <= horizonBars; step++) {
    final center = current * math.exp(mean * step);
    final band = 1.96 * sigma * math.sqrt(step);
    points.add(ForecastPoint(
      step,
      center,
      center * math.exp(-band),
      center * math.exp(band),
    ));
  }
  return MarketForecast(
    currentPrice: current,
    bullishProbability: bullish,
    bearishProbability: 100 - bullish,
    volatilityPercent: sigma * math.sqrt(horizonBars) * 100,
    points: List.unmodifiable(points),
  );
}

ForecastValidation? validateMarketForecast(
  List<MarketCandle> candles, {
  int horizonBars = 12,
  int maxSamples = 120,
}) {
  if (horizonBars < 1 || maxSamples < 1) return null;
  final data = candles.toList()
    ..sort((a, b) => a.timestamp.compareTo(b.timestamp));
  if (data.length < 25 + horizonBars + 1) return null;

  final firstOrigin = math.max(25, data.length - maxSamples - horizonBars);
  var correct = 0;
  var covered = 0;
  var absoluteError = 0.0;
  var samples = 0;

  for (var origin = firstOrigin; origin + horizonBars < data.length; origin++) {
    final history = data.sublist(0, origin);
    final forecast = buildMarketForecast(history, horizonBars: horizonBars);
    if (forecast == null) continue;
    final actual = data[origin + horizonBars].close;
    if (actual <= 0) continue;
    final actualUp = actual >= forecast.currentPrice;
    final predictedUp = forecast.bullishProbability >= 50;
    if (actualUp == predictedUp) correct++;
    if (actual >= forecast.projectedLower &&
        actual <= forecast.projectedUpper) {
      covered++;
    }
    absoluteError +=
        (actual - forecast.projectedMedian).abs() / forecast.currentPrice * 100;
    samples++;
  }

  if (samples == 0) return null;
  return ForecastValidation(
    samples: samples,
    directionalAccuracyPercent: correct / samples * 100,
    intervalCoveragePercent: covered / samples * 100,
    meanAbsoluteErrorPercent: absoluteError / samples,
  );
}
