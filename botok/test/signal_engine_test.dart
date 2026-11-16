import 'package:flutter_test/flutter_test.dart';
import 'package:botok/signal_engine.dart';

void main() {
  group('signal engine', () {
    test('neutral input starts at 50/50', () {
      final signal = calculateSignal(prices: [100, 100]);
      expect(signal.longProbability, 50);
      expect(signal.shortProbability, 50);
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
