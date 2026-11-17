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
    this.fundingRate = 0,
    this.openInterestChangePercent = 0,
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
  final double fundingRate;
  final double openInterestChangePercent;

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

  String get recommendation {
    if (!isAligned || signal.confidence < 60) return 'ЖДАТЬ';
    return signal.direction;
  }
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
    this.autoProfitTargetPercent = 0,
    this.tickSize = 0,
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
  final double autoProfitTargetPercent;
  final double tickSize;
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



double? calculateReturnCorrelation(
  List<MarketCandle> instrument,
  List<MarketCandle> benchmark, {
  int minSamples = 30,
}) {
  Map<int, double> returns(List<MarketCandle> candles) {
    final sorted = candles.where((c) => c.isClosed && c.close > 0).toList()
      ..sort((a, b) => a.timestamp.compareTo(b.timestamp));
    final output = <int, double>{};
    for (var i = 1; i < sorted.length; i++) {
      final current = sorted[i];
      final previous = sorted[i - 1];
      if (current.timestamp.difference(previous.timestamp).inSeconds > 180) continue;
      output[current.timestamp.millisecondsSinceEpoch] = math.log(current.close / previous.close);
    }
    return output;
  }

  final left = returns(instrument);
  final right = returns(benchmark);
  final keys = left.keys.where(right.containsKey).toList()..sort();
  if (keys.length < minSamples) return null;
  final x = keys.map((key) => left[key]!).toList();
  final y = keys.map((key) => right[key]!).toList();
  final meanX = x.reduce((a, b) => a + b) / x.length;
  final meanY = y.reduce((a, b) => a + b) / y.length;
  var covariance = 0.0;
  var varianceX = 0.0;
  var varianceY = 0.0;
  for (var i = 0; i < x.length; i++) {
    final dx = x[i] - meanX;
    final dy = y[i] - meanY;
    covariance += dx * dy;
    varianceX += dx * dx;
    varianceY += dy * dy;
  }
  if (varianceX <= 0 || varianceY <= 0) return null;
  return (covariance / math.sqrt(varianceX * varianceY))
      .clamp(-1.0, 1.0).toDouble();
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

TechnicalIndicators? calculateTechnicalIndicators(List<MarketCandle> input) {
  final candles = input.where((c) => c.isClosed && c.close > 0).toList()
    ..sort((a, b) => a.timestamp.compareTo(b.timestamp));
  if (candles.length < 35) return null;
  final closes = candles.map((c) => c.close).toList();
  final last = candles.last;
  final fastK = 2 / 13;
  final slowK = 2 / 27;
  final signalK = 2 / 10;
  var fastEma = closes.first;
  var slowEma = closes.first;
  var signalEma = 0.0;
  var macdValue = 0.0;
  for (var i = 0; i < closes.length; i++) {
    if (i > 0) {
      fastEma = closes[i] * fastK + fastEma * (1 - fastK);
      slowEma = closes[i] * slowK + slowEma * (1 - slowK);
    }
    macdValue = fastEma - slowEma;
    signalEma = i == 0 ? macdValue : macdValue * signalK + signalEma * (1 - signalK);
  }
  final macdHistogram = ((macdValue - signalEma) / last.close * 1000)
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
    obv += direction.toDouble() * candles[i].volume;
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
  final minRsi = recentRsi.reduce((a, b) => math.min(a, b).toDouble());
  final maxRsi = recentRsi.reduce((a, b) => math.max(a, b).toDouble());
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
  double fundingRate = 0,
  double openInterestChangePercent = 0,
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
      : (trend * 0.20 + momentum * 0.07 +
          bookImbalance.clamp(-1.0, 1.0) * 0.18 +
          tradeDelta.clamp(-1.0, 1.0) * 0.16 +
          technical.macdHistogram * 0.11 +
          technical.bollingerPosition * 0.07 +
          (technical.vwapDistancePercent / 2).clamp(-1.0, 1.0) * 0.06 +
          technical.obvTrend * 0.05 +
          (-fundingRate / 0.0005).clamp(-1.0, 1.0) * 0.06 +
          (trend * (openInterestChangePercent / 2).clamp(0.0, 1.0)) * 0.04)
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
    fundingRate: fundingRate,
    openInterestChangePercent: openInterestChangePercent,
  );
}

MultiTimeframeAnalysis calculateMultiTimeframeAnalysis({
  required Map<String, List<double>> pricesByTimeframe,
  Map<String, List<MarketCandle>>? candlesByTimeframe,
  double bookImbalance = 0,
  double tradeDelta = 0,
  double fundingRate = 0,
  double openInterestChangePercent = 0,
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
      fundingRate: fundingRate,
      openInterestChangePercent: openInterestChangePercent,
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
    fundingRate: fundingRate,
    openInterestChangePercent: openInterestChangePercent,
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
  double autoProfitTargetPercent = 0,
  bool useFullCollateral = false,
  double contractSize = 0,
  double lotSize = 0,
  double minSize = 0,
  double tickSize = 0,
}) {
  if (!entry.isFinite || entry <= 0 ||
      !capital.isFinite || capital <= 0 ||
      !riskPercent.isFinite || riskPercent <= 0 ||
      !leverage.isFinite || leverage < 1 || leverage > 100 ||
      !stopPercent.isFinite || stopPercent <= 0 ||
      !autoProfitTargetPercent.isFinite || autoProfitTargetPercent < 0 ||
      !contractSize.isFinite || contractSize < 0 ||
      !lotSize.isFinite || lotSize < 0 ||
      !minSize.isFinite || minSize < 0 ||
      !tickSize.isFinite || tickSize < 0 ||
      (direction != 'LONG' && direction != 'SHORT')) {
    throw ArgumentError('Entry, collateral, risk, stop, direction, leverage and instrument sizes must be valid.');
  }
  final isLong = direction == 'LONG';
  final normalizedEntry = tickSize > 0
      ? (entry / tickSize).roundToDouble() * tickSize
      : entry;
  final stopDistance = normalizedEntry * stopPercent / 100;
  final rawStop = isLong ? normalizedEntry - stopDistance : normalizedEntry + stopDistance;
  final stop = tickSize > 0
      ? (isLong
          ? (rawStop / tickSize).floorToDouble()
          : (rawStop / tickSize).ceilToDouble()) * tickSize
      : rawStop;
  final requestedRisk = capital * riskPercent / 100;
  final riskLimitedQuantity = requestedRisk / stopDistance;
  final marginLimitedQuantity = capital * leverage / normalizedEntry;
  var quantity = useFullCollateral
      ? marginLimitedQuantity
      : math.min(riskLimitedQuantity, marginLimitedQuantity * 0.998).toDouble();
  if (lotSize > 0) {
    if (contractSize > 0) {
      final rawContracts = quantity / contractSize;
      final roundedContracts = (rawContracts / lotSize).floorToDouble() * lotSize;
      if (roundedContracts < minSize) {
        throw ArgumentError('Position is below the OKX minimum contract size.');
      }
      quantity = roundedContracts * contractSize;
    } else {
      quantity = (quantity / lotSize).floorToDouble() * lotSize;
      if (quantity < minSize) {
        throw ArgumentError('Position is below the OKX minimum order size.');
      }
    }
  } else if (minSize > 0 && quantity < minSize) {
    throw ArgumentError('Position is below the instrument minimum size.');
  }
  if (!quantity.isFinite || quantity <= 0) {
    throw ArgumentError('Calculated order quantity is below the instrument minimum.');
  }
  final risk = quantity * stopDistance;
  final rawTp1 = isLong
      ? normalizedEntry + stopDistance * firstTargetR
      : normalizedEntry - stopDistance * firstTargetR;
  final rawTp2 = isLong
      ? normalizedEntry + stopDistance * secondTargetR
      : normalizedEntry - stopDistance * secondTargetR;
  final tp1 = tickSize > 0
      ? (isLong
          ? (rawTp1 / tickSize).ceilToDouble()
          : (rawTp1 / tickSize).floorToDouble()) * tickSize
      : rawTp1;
  final tp2 = tickSize > 0
      ? (isLong
          ? (rawTp2 / tickSize).ceilToDouble()
          : (rawTp2 / tickSize).floorToDouble()) * tickSize
      : rawTp2;
  return TradePlan(
    entry: normalizedEntry,
    stopLoss: stop,
    takeProfit1: tp1,
    takeProfit2: tp2,
    quantity: quantity,
    riskAmount: risk,
    direction: direction,
    leverage: leverage,
    trailingStopPercent: trailingStopPercent,
    autoProfitTargetPercent: autoProfitTargetPercent,
    tickSize: tickSize,
  );
}
