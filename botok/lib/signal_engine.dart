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
  });

  final double entry;
  final double stopLoss;
  final double takeProfit1;
  final double takeProfit2;
  final double quantity;
  final double riskAmount;
  final String direction;
  final double leverage;
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
  final trend = fast == 0 ? 0.0 : ((fast - slow) / fast * 100).clamp(-1.0, 1.0).toDouble();
  final momentum = ((50 - rsi) / 50).clamp(-1.0, 1.0).toDouble();
  final raw = (trend * 0.35 + bookImbalance.clamp(-1.0, 1.0) * 0.35 +
      tradeDelta.clamp(-1.0, 1.0) * 0.20 + momentum * 0.10)
      .clamp(-1.0, 1.0).toDouble();
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

TradePlan buildTradePlan({
  required String direction,
  required double entry,
  required double capital,
  required double riskPercent,
  required double leverage,
  double stopPercent = 0.8,
  double firstTargetR = 1.5,
  double secondTargetR = 2.5,
}) {
  if (entry <= 0 || capital <= 0 || riskPercent <= 0 || leverage <= 0) {
    throw ArgumentError('Entry, capital, risk and leverage must be positive.');
  }
  final isLong = direction == 'LONG';
  final stopDistance = entry * stopPercent / 100;
  final stop = isLong ? entry - stopDistance : entry + stopDistance;
  final risk = capital * riskPercent / 100;
  final quantity = risk / stopDistance;
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
