import 'dart:math' as math;

import 'okx_market.dart';

class TradeSignal {
  const TradeSignal({
    required this.longProbability,
    required this.shortProbability,
    required this.rsi,
    required this.emaFast,
    required this.emaSlow,
    required this.bookImbalance,
    required this.tradeDelta,
    this.macdHistogram = 0,
    this.bollingerPosition = 0,
    this.atrPercent = 0,
    this.vwapDistancePercent = 0,
    this.obvTrend = 0,
    this.stochasticRsi = 50,
  });

  final double longProbability;
  final double shortProbability;
  final double rsi;
  final double emaFast;
  final double emaSlow;
  final double bookImbalance;
  final double tradeDelta;
  final double macdHistogram;
  final double bollingerPosition;
  final double atrPercent;
  final double vwapDistancePercent;
  final double obvTrend;
  final double stochasticRsi;

  String get direction => longProbability >= shortProbability ? 'LONG' : 'SHORT';
  double get confidence => math.max(longProbability, shortProbability).toDouble();
}

class MultiTimeframeAnalysis {
  const MultiTimeframeAnalysis({
    required this.signal,
    required this.byTimeframe,
    required this.activeTimeframes,
    required this.agreementPercent,
    required this.weightedScore,
  });

  final TradeSignal signal;
  final Map<String, TradeSignal> byTimeframe;
  final int activeTimeframes;
  final double agreementPercent;
  final double weightedScore;

  bool get isAligned => activeTimeframes >= 3 && agreementPercent >= 60;
}

class TradePlan {
  const TradePlan({
    required this.entry,
    required this.stopLoss,
    required this.takeProfit1,
    required this.takeProfit2,
    required this.quantity,
    required this.riskAmount,
    required this.direction,
    required this.leverage,
    this.trailingStopPercent = 1.0,
  });

  final double entry;
  final double stopLoss;
  final double takeProfit1;
  final double takeProfit2;
  final double quantity;
  final double riskAmount;
  final String direction;
  final double leverage;
  final double trailingStopPercent;
}

double _ema(List<double> values, int period) {
  if (values.isEmpty) return 0;
  final k = 2 / (period + 1);
  var result = values.first;
  for (final value in values.skip(1)) {
    result = value * k + result * (1 - k);
  }
  return result;
}

double _rsi(List<double> values) {
  if (values.length < 2) return 50;
  var gains = 0.0;
  var losses = 0.0;
  final start = math.max(1, values.length - 14).toInt();
  for (var i = start; i < values.length; i++) {
    final change = values[i] - values[i - 1];
    if (change >= 0) {
      gains += change;
    } else {
      losses -= change;
    }
  }
  if (losses == 0) return gains == 0 ? 50 : 100;
  final rs = gains / losses;
  return 100 - 100 / (1 + rs);
}


class TechnicalIndicators {
  const TechnicalIndicators({
    required this.macdHistogram,
    required this.bollingerPosition,
    required this.atrPercent,
    required this.vwapDistancePercent,
    required this.obvTrend,
    required this.stochasticRsi,
  });

  final double macdHistogram;
  final double bollingerPosition;
  final double atrPercent;
  final double vwapDistancePercent;
  final double obvTrend;
  final double stochasticRsi;
}

double _emaSeries(List<double> values, int period) => _ema(values, period);

TechnicalIndicators? calculateTechnicalIndicators(List<MarketCandle> input) {
  final candles = input.where((c) => c.isClosed && c.close > 0).toList()
    ..sort((a, b) => a.timestamp.compareTo(b.timestamp));
  if (candles.length < 35) return null;
  final closes = candles.map((c) => c.close).toList();
  final last = candles.last;
  final macdSeries = <double>[];
  for (var i = 0; i < closes.length; i++) {
    final slice = closes.sublist(0, i + 1);
    macdSeries.add(_emaSeries(slice, 12) - _emaSeries(slice, 26));
  }
  final macdSignal = _emaSeries(macdSeries, 9);
  final macdHistogram = ((macdSeries.last - macdSignal) / last.close * 1000)
      .clamp(-1.0, 1.0).toDouble();

  final window = candles.skip(candles.length - 20).toList();
  final mean = window.fold<double>(0, (sum, c) => sum + c.close) / window.length;
  final variance = window.fold<double>(0, (sum, c) => sum + math.pow(c.close - mean, 2).toDouble()) / window.length;
  final deviation = math.sqrt(variance);
  final bollinger = deviation == 0 ? 0.0 : ((last.close - mean) / (2 * deviation)).clamp(-1.0, 1.0).toDouble();

  var trueRange = 0.0;
  for (var i = candles.length - 14; i < candles.length; i++) {
    final candle = candles[i];
    final previous = candles[i - 1].close;
    trueRange += math.max(candle.high - candle.low, math.max((candle.high - previous).abs(), (candle.low - previous).abs())).toDouble();
  }
  final atrPercent = trueRange / 14 / last.close * 100;

  var volumeSum = 0.0;
  var valueSum = 0.0;
  for (final candle in window) {
    final typical = (candle.high + candle.low + candle.close) / 3;
    final volume = math.max(0, candle.volume).toDouble();
    volumeSum += volume;
    valueSum += typical * volume;
  }
  final vwap = volumeSum == 0 ? last.close : valueSum / volumeSum;
  final vwapDistance = ((last.close - vwap) / last.close * 100).clamp(-5.0, 5.0).toDouble();

  var obv = 0.0;
  final obvValues = <double>[0];
  for (var i = 1; i < candles.length; i++) {
    final direction = candles[i].close.compareTo(candles[i - 1].close);
    obv += direction * candles[i].volume;
    obvValues.add(obv);
  }
  final obvRecent = obvValues.skip(obvValues.length - 10).reduce((a, b) => a + b) / 10;
  final obvPrior = obvValues.skip(obvValues.length - 20).take(10).reduce((a, b) => a + b) / 10;
  final obvScale = candles.skip(candles.length - 20).fold<double>(0, (sum, c) => sum + c.volume.abs()) + 1e-12;
  final obvTrend = ((obvRecent - obvPrior) / obvScale).clamp(-1.0, 1.0).toDouble();

  final rsiValues = <double>[];
  for (var i = 15; i <= closes.length; i++) {
    rsiValues.add(_rsi(closes.sublist(0, i)));
  }
  final recentRsi = rsiValues.skip(math.max(0, rsiValues.length - 14).toInt()).toList();
  final minRsi = recentRsi.reduce(math.min);
  final maxRsi = recentRsi.reduce(math.max);
  final stochastic = maxRsi == minRsi ? 50.0 : ((recentRsi.last - minRsi) / (maxRsi - minRsi) * 100).clamp(0.0, 100.0).toDouble();

  return TechnicalIndicators(
    macdHistogram: macdHistogram,
    bollingerPosition: bollinger,
    atrPercent: atrPercent,
    vwapDistancePercent: vwapDistance,
    obvTrend: obvTrend,
    stochasticRsi: stochastic,
  );
}

TradeSignal calculateSignal({
  required List<double> prices,
  double bookImbalance = 0,
  double tradeDelta = 0,
  List<MarketCandle>? candles,
}) {
  if (prices.length < 2) {
    return const TradeSignal(
      longProbability: 50,
      shortProbability: 50,
      rsi: 50,
      emaFast: 0,
      emaSlow: 0,
      bookImbalance: 0,
      tradeDelta: 0,
    );
  }
  final fast = _ema(prices, math.min(9, prices.length).toInt());
  final slow = _ema(prices, math.min(21, prices.length).toInt());
  final rsi = _rsi(prices);
  final trend = fast == 0
      ? 0.0
      : ((fast - slow) / fast * 100).clamp(-1.0, 1.0).toDouble();
  final momentum = ((rsi - 50) / 50).clamp(-1.0, 1.0).toDouble();
  final technical = candles == null ? null : calculateTechnicalIndicators(candles);
  final raw = technical == null
      ? (trend * 0.35 + momentum * 0.10 +
          bookImbalance.clamp(-1.0, 1.0) * 0.30 +
          tradeDelta.clamp(-1.0, 1.0) * 0.25)
      : (trend * 0.22 + momentum * 0.08 +
          bookImbalance.clamp(-1.0, 1.0) * 0.20 +
          tradeDelta.clamp(-1.0, 1.0) * 0.18 +
          technical.macdHistogram * 0.12 +
          technical.bollingerPosition * 0.08 +
          (technical.vwapDistancePercent / 2).clamp(-1.0, 1.0) * 0.07 +
          technical.obvTrend * 0.05)
      .clamp(-1.0, 1.0)
      .toDouble();
  final long = (50 + raw * 45).clamp(5.0, 95.0).toDouble();
  return TradeSignal(
    longProbability: long,
    shortProbability: 100 - long,
    rsi: rsi,
    emaFast: fast,
    emaSlow: slow,
    bookImbalance: bookImbalance,
    tradeDelta: tradeDelta,
    macdHistogram: technical?.macdHistogram ?? 0,
    bollingerPosition: technical?.bollingerPosition ?? 0,
    atrPercent: technical?.atrPercent ?? 0,
    vwapDistancePercent: technical?.vwapDistancePercent ?? 0,
    obvTrend: technical?.obvTrend ?? 0,
    stochasticRsi: technical?.stochasticRsi ?? 50,
  );
}

MultiTimeframeAnalysis calculateMultiTimeframeAnalysis({
  required Map<String, List<double>> pricesByTimeframe,
  Map<String, List<MarketCandle>>? candlesByTimeframe,
  double bookImbalance = 0,
  double tradeDelta = 0,
}) {
  const weights = <String, double>{
    '1m': 0.5,
    '3m': 0.75,
    '5m': 1.0,
    '15m': 1.25,
    '1H': 1.5,
    '1D': 1.75,
    '1W': 2.0,
  };
  final byTimeframe = <String, TradeSignal>{};
  var weighted = 0.0;
  var totalWeight = 0.0;
  var longWeight = 0.0;
  var rsiWeighted = 0.0;
  var rsiWeight = 0.0;

  for (final entry in weights.entries) {
    final prices = pricesByTimeframe[entry.key];
    if (prices == null || prices.length < 25) continue;
    final shortTerm = entry.key == '1m';
    final signal = calculateSignal(
      prices: prices,
      candles: candlesByTimeframe?[entry.key],
      bookImbalance: shortTerm ? bookImbalance : 0,
      tradeDelta: shortTerm ? tradeDelta : 0,
    );
    byTimeframe[entry.key] = signal;
    final weight = entry.value;
    final score = (signal.longProbability - 50) / 45;
    weighted += score * weight;
    totalWeight += weight;
    rsiWeighted += signal.rsi * weight;
    rsiWeight += weight;
  }

  final score = totalWeight == 0
      ? 0.0
      : (weighted / totalWeight).clamp(-1.0, 1.0).toDouble();
  final long = (50 + score * 45).clamp(5.0, 95.0).toDouble();
  final direction = score >= 0 ? 'LONG' : 'SHORT';
  for (final entry in byTimeframe.entries) {
    final aligned = direction == 'LONG'
        ? entry.value.longProbability >= 50
        : entry.value.shortProbability > 50;
    if (aligned) longWeight += weights[entry.key]!;
  }
  final agreement = totalWeight == 0 ? 0.0 : longWeight / totalWeight * 100;
  final oneMinute = byTimeframe['1m'];
  final signal = TradeSignal(
    longProbability: long,
    shortProbability: 100 - long,
    rsi: rsiWeight == 0 ? 50 : rsiWeighted / rsiWeight,
    emaFast: oneMinute?.emaFast ?? 0,
    emaSlow: oneMinute?.emaSlow ?? 0,
    bookImbalance: bookImbalance,
    tradeDelta: tradeDelta,
    macdHistogram: oneMinute?.macdHistogram ?? 0,
    bollingerPosition: oneMinute?.bollingerPosition ?? 0,
    atrPercent: oneMinute?.atrPercent ?? 0,
    vwapDistancePercent: oneMinute?.vwapDistancePercent ?? 0,
    obvTrend: oneMinute?.obvTrend ?? 0,
    stochasticRsi: oneMinute?.stochasticRsi ?? 50,
  );
  return MultiTimeframeAnalysis(
    signal: signal,
    byTimeframe: Map.unmodifiable(byTimeframe),
    activeTimeframes: byTimeframe.length,
    agreementPercent: agreement,
    weightedScore: score,
  );
}

TradePlan buildTradePlan({
  required String direction,
  required double entry,
  required double capital,
  required double riskPercent,
  required double leverage,
  double stopPercent = 0.8,
  double firstTargetR = 1.5,
  double secondTargetR = 2.5,
  double trailingStopPercent = 1.0,
}) {
  if (entry <= 0 ||
      capital <= 0 ||
      riskPercent <= 0 ||
      leverage <= 0 ||
      stopPercent <= 0 ||
      (direction != 'LONG' && direction != 'SHORT')) {
    throw ArgumentError('Entry, capital, risk, stop, direction and leverage must be valid.');
  }
  final isLong = direction == 'LONG';
  final stopDistance = entry * stopPercent / 100;
  final stop = isLong ? entry - stopDistance : entry + stopDistance;
  final requestedRisk = capital * riskPercent / 100;
  final riskLimitedQuantity = requestedRisk / stopDistance;
  final marginLimitedQuantity = capital * leverage * 0.998 / entry;
  final quantity = math.min(riskLimitedQuantity, marginLimitedQuantity).toDouble();
  final risk = quantity * stopDistance;
  final tp1 = isLong
      ? entry + stopDistance * firstTargetR
      : entry - stopDistance * firstTargetR;
  final tp2 = isLong
      ? entry + stopDistance * secondTargetR
      : entry - stopDistance * secondTargetR;
  return TradePlan(
    entry: entry,
    stopLoss: stop,
    takeProfit1: tp1,
    takeProfit2: tp2,
    quantity: quantity,
    riskAmount: risk,
    direction: direction,
    leverage: leverage,
  );
}
