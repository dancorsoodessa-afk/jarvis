import 'package:flutter_test/flutter_test.dart';
import 'package:botok/paper_trading.dart';
import 'package:botok/signal_engine.dart';

void main() {
  TradePlan plan() => buildTradePlan(
    direction: 'LONG',
    entry: 100,
    capital: 1000,
    riskPercent: 1,
    leverage: 2,
  );

  group('PaperTradingEngine', () {
    test('opening a position locks margin and charges entry fee', () {
      final paper = PaperTradingEngine(initialBalance: 1000, feeRate: 0.001);
      final position = paper.open(plan(), instrumentId: 'BTC-USDT');
      expect(position.margin, greaterThan(0));
      expect(paper.marginUsed, closeTo(position.margin, 1e-8));
      expect(paper.availableBalance, lessThan(1000));
      expect(paper.totalFees, greaterThan(0));
      expect(paper.openPosition, isNotNull);
    });

    test('automatic profit target closes full position at net percentage of initial margin', () {
      final autoPlan = buildTradePlan(
        direction: 'LONG',
        entry: 100,
        capital: 1000,
        riskPercent: 1,
        leverage: 2,
        autoProfitTargetPercent: 5,
      );
      final paper = PaperTradingEngine(initialBalance: 1000, feeRate: 0);
      paper.open(autoPlan, instrumentId: 'BTC-USDT-SWAP');
      final closed = paper.markPrice(102.6);
      expect(closed, isNotNull);
      expect(closed!.reason, 'AUTO_PROFIT_TARGET');
      expect(paper.openPosition, isNull);
      expect(closed.realizedPnl / (autoPlan.entry * autoPlan.quantity / autoPlan.leverage) * 100, greaterThanOrEqualTo(5));
    });

    test('automatic profit target persists after wallet restore', () {
      final autoPlan = buildTradePlan(
        direction: 'SHORT',
        entry: 100,
        capital: 1000,
        riskPercent: 1,
        leverage: 3,
        autoProfitTargetPercent: 4.5,
      );
      final paper = PaperTradingEngine(initialBalance: 1000, feeRate: 0);
      paper.open(autoPlan, instrumentId: 'BTC-USDT-SWAP');
      final restored = PaperTradingEngine.decode(paper.encode());
      expect(restored.openPosition!.plan.autoProfitTargetPercent, 4.5);
    });

    test('live equity and account PnL include estimated exit fee', () {
      final paper = PaperTradingEngine(initialBalance: 1000, feeRate: 0.001);
      final opened = paper.open(plan(), instrumentId: 'BTC-USDT-SWAP');
      paper.markPrice(101);
      final position = paper.openPosition!;
      final expectedNet = position.partialRealizedPnl + position.unrealizedPnl -
          position.entryFee - position.partialFees -
          position.currentPrice * position.quantity * paper.feeRate;
      expect(paper.positionNetPnl, closeTo(expectedNet, 1e-8));
      expect(paper.equity, closeTo(paper.cashBalance + paper.unrealizedPnl -
          position.currentPrice * position.quantity * paper.feeRate, 1e-8));
      expect(paper.netAccountPnl, closeTo(paper.equity - paper.initialBalance, 1e-8));
      expect(paper.equity, lessThan(paper.cashBalance + paper.unrealizedPnl));
      expect(opened.entryFee, greaterThan(0));
    });

    test('mark price updates unrealized PnL and equity', () {
      final paper = PaperTradingEngine(initialBalance: 1000, feeRate: 0);
      paper.open(plan(), instrumentId: 'BTC-USDT');
      paper.markPrice(101);
      expect(paper.unrealizedPnl, greaterThan(0));
      expect(paper.equity, greaterThan(1000));
    });

    test('stop loss closes position, releases margin and realizes loss', () {
      final paper = PaperTradingEngine(initialBalance: 1000, feeRate: 0);
      paper.open(plan(), instrumentId: 'BTC-USDT');
      final closed = paper.markPrice(plan().stopLoss - 0.01);
      expect(closed, isNotNull);
      expect(paper.openPosition, isNull);
      expect(paper.marginUsed, 0);
      expect(paper.realizedPnl, lessThan(0));
      expect(paper.closedTrades, hasLength(1));
    });

    test('take profit one partially realizes and take profit two closes remainder', () {
      final paper = PaperTradingEngine(initialBalance: 1000, feeRate: 0);
      paper.open(plan(), instrumentId: 'BTC-USDT');
      paper.markPrice(plan().takeProfit1);
      expect(paper.openPosition, isNotNull);
      expect(paper.openPosition!.quantity, closeTo(plan().quantity * 0.5, 1e-8));
      paper.markPrice(plan().takeProfit2);
      expect(paper.openPosition, isNull);
      expect(paper.closedTrades, hasLength(1));
      expect(paper.realizedPnl, greaterThan(0));
    });

    test('stop loss does not create phantom balance by returning unspent margin', () {
      final paper = PaperTradingEngine(initialBalance: 1000, feeRate: 0.001);
      final p = paper.open(plan(), instrumentId: 'BTC-USDT');
      final before = paper.cashBalance;
      final closed = paper.markPrice(plan().stopLoss);
      expect(closed, isNotNull);
      expect(paper.cashBalance, lessThan(1000));
      expect(paper.cashBalance, closeTo(before + (plan().stopLoss - plan().entry) * p.quantity - plan().stopLoss * p.quantity * 0.001, 1e-6));
      expect(paper.equity, closeTo(paper.cashBalance, 1e-8));
      expect(paper.marginUsed, 0);
    });

    test('TP1 partial close does not credit reserved margin twice', () {
      final paper = PaperTradingEngine(initialBalance: 1000, feeRate: 0.001);
      final p = paper.open(plan(), instrumentId: 'BTC-USDT');
      final before = paper.cashBalance;
      final price = plan().takeProfit1;
      paper.markPrice(price);
      final partialQty = p.quantity * 0.5;
      final expectedCash = before + (price - plan().entry) * partialQty - price * partialQty * 0.001;
      expect(paper.cashBalance, closeTo(expectedCash, 1e-6));
      expect(paper.marginUsed, closeTo(p.margin * 0.5, 1e-8));
    });

    test('closed trade net result matches account equity change', () {
      final paper = PaperTradingEngine(initialBalance: 1000, feeRate: 0.001);
      paper.open(plan(), instrumentId: 'BTC-USDT');
      final closed = paper.markPrice(plan().stopLoss);
      expect(closed, isNotNull);
      expect(paper.netAccountPnl, closeTo(closed!.realizedPnl - closed.fees, 1e-6));
    });

    test('cannot open a second position or exceed available margin', () {
      final paper = PaperTradingEngine(initialBalance: 1, feeRate: 0);
      expect(() => paper.open(plan(), instrumentId: 'BTC-USDT'), throwsStateError);
    });

    test('a direct jump across TP1 and TP2 records TP1 before closing the remainder', () {
      final paper = PaperTradingEngine(initialBalance: 1000, feeRate: 0);
      paper.open(plan(), instrumentId: 'BTC-USDT');
      final closed = paper.markPrice(plan().takeProfit2);
      expect(closed, isNotNull);
      expect(closed!.reason, 'TAKE_PROFIT_2');
      final expected = (plan().takeProfit1 - plan().entry) * plan().quantity * 0.5 +
          (plan().takeProfit2 - plan().entry) * plan().quantity * 0.5;
      expect(closed.realizedPnl, closeTo(expected, 1e-6));
      expect(paper.openPosition, isNull);
    });

    test('trailing stop follows favourable price and protects accumulated movement', () {
      final paper = PaperTradingEngine(initialBalance: 1000, feeRate: 0);
      paper.open(plan(), instrumentId: 'BTC-USDT');
      paper.markPrice(101);
      expect(paper.openPosition!.trailingStopPrice, greaterThan(plan().stopLoss));
      final closed = paper.markPrice(99.9);
      expect(closed, isNotNull);
      expect(closed!.reason, 'TRAILING_STOP');
      expect(paper.openPosition, isNull);
    });

    test('trailing stop state survives wallet persistence', () {
      final paper = PaperTradingEngine(initialBalance: 1000, feeRate: 0);
      paper.open(plan(), instrumentId: 'BTC-USDT');
      paper.markPrice(101);
      final restored = PaperTradingEngine.decode(paper.encode());
      expect(
        restored.openPosition!.trailingStopPrice,
        closeTo(paper.openPosition!.trailingStopPrice!, 1e-8),
      );
      expect(restored.openPosition!.bestPrice, 101);
    });

    test('wallet and trade history survive JSON round trip', () {
      final paper = PaperTradingEngine(initialBalance: 1000, feeRate: 0.001);
      paper.open(plan(), instrumentId: 'BTC-USDT');
      paper.markPrice(101);
      final restored = PaperTradingEngine.fromJson(paper.toJson());
      expect(restored.availableBalance, closeTo(paper.availableBalance, 1e-8));
      expect(restored.equity, closeTo(paper.equity, 1e-8));
      expect(restored.openPosition!.plan.entry, 100);
      expect(restored.openPosition!.instrumentId, 'BTC-USDT');
    });
  });
}
