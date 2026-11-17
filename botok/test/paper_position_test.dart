import 'package:flutter_test/flutter_test.dart';
import 'package:botok/paper_position.dart';
import 'package:botok/signal_engine.dart';

void main() {
  group('PaperPosition', () {
    AllocationPlan plan(String direction) => buildAllocationPlan(
      direction: direction,
      entry: 100,
      quoteBalance: 100,
      allocationPercent: 10,
      targetNetPercent: 1,
      feeRate: 0.001,
    );

    test('long position exits at stop and take-profit boundaries', () {
      final position = PaperPosition.fromPlan(plan('LONG'), instrumentId: 'BTC-USDT');
      expect(position.exitReasonAt(position.stopLoss), PaperExitReason.stopLoss);
      expect(position.exitReasonAt(position.takeProfit), PaperExitReason.takeProfit);
      expect(position.exitReasonAt(100), isNull);
    });

    test('short position exits at inverse stop and take-profit boundaries', () {
      final position = PaperPosition.fromPlan(plan('SHORT'), instrumentId: 'BTC-USDT-SWAP');
      expect(position.exitReasonAt(position.stopLoss), PaperExitReason.stopLoss);
      expect(position.exitReasonAt(position.takeProfit), PaperExitReason.takeProfit);
      expect(position.exitReasonAt(100), isNull);
    });

    test('position survives serialization with its risk and fee values', () {
      final original = PaperPosition.fromPlan(plan('LONG'), instrumentId: 'ETH-USDT');
      final restored = PaperPosition.fromJson(original.toJson());
      expect(restored.instrumentId, original.instrumentId);
      expect(restored.direction, original.direction);
      expect(restored.entry, original.entry);
      expect(restored.stopLoss, original.stopLoss);
      expect(restored.takeProfit, original.takeProfit);
      expect(restored.quantity, original.quantity);
      expect(restored.netTarget, closeTo(original.netTarget, 1e-10));
    });

    test('net PnL includes entry and exit fees', () {
      final position = PaperPosition.fromPlan(plan('LONG'), instrumentId: 'BTC-USDT');
      expect(position.netPnlAt(position.takeProfit), closeTo(position.netTarget, 1e-8));
      expect(position.netPnlAt(position.stopLoss), lessThan(0));
    });
  });
}
