import 'dart:math' as math;

class TrendOutlook {
  const TrendOutlook({
    required this.direction,
    required this.confidence,
    required this.lastPrice,
    required this.projectedPrices,
    required this.emaFast,
    required this.emaSlow,
    required this.rsi,
    required this.momentumPercent,
    required this.horizonLabel,
  });

  final String direction;
  final double confidence;
  final double lastPrice;
  final List<double> projectedPrices;
  final double emaFast;
  final double emaSlow;
  final double rsi;
  final double momentumPercent;
  final String horizonLabel;
}

double _ema(List<double> values, int period) {
  final k = 2 / (period + 1);
  var value = values.first;
  for (final next in values.skip(1)) {
    value = next * k + value * (1 - k);
  }
  return value;
}

/// A transparent technical extrapolation, not a machine-learning prediction.
TrendOutlook calculateTrendOutlook(List<double> input) {
  final values = input.where((v) => v.isFinite && v > 0).toList();
  if (values.length < 30) {
    return const TrendOutlook(
      direction: 'NEUTRAL',
      confidence: 0,
      lastPrice: 0,
      projectedPrices: [],
      emaFast: 0,
      emaSlow: 0,
      rsi: 50,
      momentumPercent: 0,
      horizonLabel: 'Недостаточно данных',
    );
  }

  final recent = values.length > 24 ? values.sublist(values.length - 24) : values;
  final fast = _ema(values, 9);
  final slow = _ema(values, 21);
  var gains = 0.0;
  var losses = 0.0;
  for (var i = math.max(1, values.length - 14); i < values.length; i++) {
    final change = values[i] - values[i - 1];
    if (change >= 0) {
      gains += change;
    } else {
      losses -= change;
    }
  }
  final rsi = losses == 0 ? (gains == 0 ? 50.0 : 100.0) : 100 - 100 / (1 + gains / losses);

  // Least-squares slope on the latest 24 closes, expressed as % per candle.
  final n = recent.length;
  final meanX = (n - 1) / 2;
  final meanY = recent.reduce((a, b) => a + b) / n;
  var numerator = 0.0;
  var denominator = 0.0;
  for (var i = 0; i < n; i++) {
    numerator += (i - meanX) * (recent[i] - meanY);
    denominator += (i - meanX) * (i - meanX);
  }
  final slope = denominator == 0 ? 0.0 : numerator / denominator;
  final last = values.last;
  final slopePct = slope / last * 100;
  final emaPct = (fast - slow) / last * 100;
  final momentum = (slopePct * 0.7 + emaPct * 0.3).clamp(-1.5, 1.5).toDouble();
  final aligned = (fast >= slow && momentum >= 0) || (fast < slow && momentum < 0);
  final direction = momentum.abs() < 0.015
      ? 'NEUTRAL'
      : momentum > 0 ? 'BULLISH' : 'BEARISH';
  final rsiPenalty = (rsi > 75 && direction == 'BULLISH') || (rsi < 25 && direction == 'BEARISH') ? 12.0 : 0.0;
  final confidence = (50 + momentum.abs() * 18 + (aligned ? 12 : 0) - rsiPenalty)
      .clamp(50.0, 85.0).toDouble();
  final step = slope.clamp(-last * 0.01, last * 0.01).toDouble();
  final projected = List<double>.generate(3, (i) => math.max(0.00000001, last + step * (i + 1)).toDouble());

  return TrendOutlook(
    direction: direction,
    confidence: confidence,
    lastPrice: last,
    projectedPrices: projected,
    emaFast: fast,
    emaSlow: slow,
    rsi: rsi,
    momentumPercent: momentum,
    horizonLabel: 'Следующие 1–3 свечи',
  );
}
