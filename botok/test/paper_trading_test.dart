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
