import 'dart:math' as math;

class TradeSignal {
  const TradeSignal({
    required this.longProbability,
    required this.shortProbability,
    required this.rsi,
    required this.emaFast,
    required this.emaSlow,
    required this.bookImbalance,
    required this.tradeDelta,
  });

  final double longProbability;
  final double shortProbability;
  final double rsi;
  final double emaFast;
  final double emaSlow;
  final double bookImbalance;
  final double tradeDelta;

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

TradeSignal calculateSignal({
  required List<double> prices,
  double bookImbalance = 0,
  double tradeDelta = 0,
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
  final raw = (trend * 0.35 +
          momentum * 0.10 +
          bookImbalance.clamp(-1.0, 1.0) * 0.30 +
          tradeDelta.clamp(-1.0, 1.0) * 0.25)
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
  );
}

MultiTimeframeAnalysis calculateMultiTimeframeAnalysis({
  required Map<String, List<double>> pricesByTimeframe,
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
  var shortWeight = 0.0;
  var rsiWeighted = 0.0;
  var rsiWeight = 0.0;

  for (final entry in weights.entries) {
    final prices = pricesByTimeframe[entry.key];
    if (prices == null || prices.length < 25) continue;
    final shortTerm = entry.key == '1m';
    final signal = calculateSignal(
      prices: prices,
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
