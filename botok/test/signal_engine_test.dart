import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:botok/signal_engine.dart';
import 'package:botok/okx_market.dart';

void main() {
  group('signal engine', () {


    test('BTC correlation uses aligned timestamped returns and stays bounded', () {
      final benchmark = List.generate(100, (index) {
        final close = 100 + index.toDouble();
        return MarketCandle(
          timestamp: DateTime.utc(2026).add(Duration(minutes: index)),
          open: close - 1,
          high: close + 1,
          low: close - 2,
          close: close,
          volume: 100,
          isClosed: true,
        );
      });
      final correlated = List.generate(100, (index) {
        final close = 200 + index * 2.0;
        return MarketCandle(
          timestamp: DateTime.utc(2026).add(Duration(minutes: index)),
          open: close - 2,
          high: close + 2,
          low: close - 3,
          close: close,
          volume: 80,
          isClosed: true,
        );
      });
      final result = calculateReturnCorrelation(correlated, benchmark);
      expect(result, isNotNull);
      expect(result!, inInclusiveRange(-1, 1));
      expect(result, closeTo(1, 0.0001));
    });

    test('technical indicators calculate finite MACD, Bollinger, ATR, VWAP, OBV and Stoch RSI', () {
      var price = 100.0;
      final candles = List.generate(80, (index) {
        final open = price;
        price *= 1 + (index.isEven ? 0.0015 : -0.0004);
        return MarketCandle(
          timestamp: DateTime.utc(2026).add(Duration(minutes: index)),
          open: open,
          high: math.max(open, price).toDouble() * 1.002,
          low: math.min(open, price).toDouble() * 0.998,
          close: price,
          volume: 10 + index.toDouble(),
          isClosed: true,
        );
      });
      final result = calculateTechnicalIndicators(candles);
      expect(result, isNotNull);
      expect(result!.macdHistogram.isFinite, isTrue);
      expect(result.bollingerPosition, inInclusiveRange(-1, 1));
      expect(result.atrPercent, greaterThan(0));
      expect(result.vwapDistancePercent.isFinite, isTrue);
      expect(result.obvTrend, inInclusiveRange(-1, 1));
      expect(result.stochasticRsi, inInclusiveRange(0, 100));
    });

    test('neutral input starts at 50/50', () {
      final signal = calculateSignal(prices: [100, 100]);
      expect(signal.longProbability, 50);
      expect(signal.shortProbability, 50);
    });

    test('recommendation waits when fewer than two timeframes are active', () {
      const analysis = MultiTimeframeAnalysis(
        signal: TradeSignal(longProbability: 80, shortProbability: 20, rsi: 60, emaFast: 101, emaSlow: 100, bookImbalance: 0, tradeDelta: 0),
        byTimeframe: {},
        activeTimeframes: 1,
        agreementPercent: 100,
        weightedScore: 0.6,
      );
      expect(analysis.recommendation, 'ЖДАТЬ');
    });

    test('recommendation returns LONG when score and timeframe agreement are sufficient', () {
      const analysis = MultiTimeframeAnalysis(
        signal: TradeSignal(longProbability: 70, shortProbability: 30, rsi: 60, emaFast: 101, emaSlow: 100, bookImbalance: 0, tradeDelta: 0),
        byTimeframe: {},
        activeTimeframes: 2,
        agreementPercent: 60,
        weightedScore: 0.4,
      );
      expect(analysis.recommendation, 'LONG');
    });

    test('recommendation waits when timeframe agreement is weak', () {
      const analysis = MultiTimeframeAnalysis(
        signal: TradeSignal(longProbability: 70, shortProbability: 30, rsi: 60, emaFast: 101, emaSlow: 100, bookImbalance: 0, tradeDelta: 0),
        byTimeframe: {},
        activeTimeframes: 2,
        agreementPercent: 50,
        weightedScore: 0.4,
      );
      expect(analysis.recommendation, 'ЖДАТЬ');
    });

    test('probabilities always sum to 100 and stay bounded', () {
      final signal = calculateSignal(
        prices: List<double>.generate(40, (i) => 100 + i.toDouble()),
        bookImbalance: 0.8,
        tradeDelta: 0.7,
      );
      expect(signal.longProbability + signal.shortProbability, closeTo(100, 0.0001));
      expect(signal.longProbability, inInclusiveRange(5, 95));
    });

    test('long plan calculates stop and two targets', () {
      final plan = buildTradePlan(
        direction: 'LONG',
        entry: 100,
        capital: 1000,
        riskPercent: 1,
        leverage: 2,
      );
      expect(plan.stopLoss, lessThan(plan.entry));
      expect(plan.takeProfit1, greaterThan(plan.entry));
      expect(plan.takeProfit2, greaterThan(plan.takeProfit1));
      expect(plan.riskAmount, 10);
    });

    test('short plan mirrors long levels', () {
      final plan = buildTradePlan(
        direction: 'SHORT',
        entry: 100,
        capital: 1000,
        riskPercent: 1,
        leverage: 2,
      );
      expect(plan.stopLoss, greaterThan(plan.entry));
      expect(plan.takeProfit1, lessThan(plan.entry));
      expect(plan.takeProfit2, lessThan(plan.takeProfit1));
    });

    test('automatic plan uses the requested collateral as margin, not as risk budget', () {
      final plan = buildTradePlan(
        direction: 'LONG',
        entry: 100,
        capital: 10,
        riskPercent: 1,
        leverage: 5,
        useFullCollateral: true,
      );
      expect(plan.entry * plan.quantity / plan.leverage, closeTo(10, 1e-8));
      expect(plan.entry * plan.quantity, closeTo(50, 1e-8));
    });

    test('invalid capital is rejected', () {
      expect(() => buildTradePlan(
        direction: 'LONG',
        entry: 100,
        capital: 0,
        riskPercent: 1,
        leverage: 1,
      ), throwsArgumentError);
    });
  });
}
