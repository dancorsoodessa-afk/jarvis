import 'dart:math' as math;

import 'okx_market.dart';
import 'signal_engine.dart';

class BacktestConfig {
  const BacktestConfig({
    this.riskPercent = 1,
    this.stopPercent = 0.8,
    this.firstTargetR = 1.5,
    this.secondTargetR = 2.5,
    this.trailingStopPercent = 1.0,
    this.feeRate = 0.001,
    this.slippageBps = 3,
    this.signalThreshold = 60,
    this.maxDrawdownPercent = 20,
    this.startingBalance = 1000,
  });

  final double riskPercent;
  final double stopPercent;
  final double firstTargetR;
  final double secondTargetR;
  final double trailingStopPercent;
  final double feeRate;
  final double slippageBps;
  final double signalThreshold;
  final double maxDrawdownPercent;
  final double startingBalance;
}

class BacktestTrade {
  const BacktestTrade(
    this.direction,
    this.entry,
    this.exit,
    this.netPnl,
    this.reason,
    this.entryIndex,
    this.exitIndex,
  );

  final String direction;
  final String reason;
  final double entry;
  final double exit;
  final double netPnl;
  final int entryIndex;
  final int exitIndex;
}

class BacktestResult {
  const BacktestResult({
    required this.trades,
    required this.finalBalance,
    required this.netPnl,
    required this.returnPercent,
    required this.winRate,
    required this.profitFactor,
    required this.maxDrawdownPercent,
    required this.equityCurve,
    required this.fees,
    required this.buyHoldReturnPercent,
  });

  final List<BacktestTrade> trades;
  final double finalBalance;
  final double netPnl;
  final double returnPercent;
  final double winRate;
  final double profitFactor;
  final double maxDrawdownPercent;
  final List<double> equityCurve;
  final double fees;
  final double buyHoldReturnPercent;

  int get tradeCount => trades.length;
}

class WalkForwardFold {
  const WalkForwardFold(
    this.trainStart,
    this.trainEnd,
    this.testStart,
    this.testEnd,
    this.selectedConfig,
    this.testResult,
  );

  final int trainStart;
  final int trainEnd;
  final int testStart;
  final int testEnd;
  final BacktestConfig selectedConfig;
  final BacktestResult testResult;
}

class WalkForwardResult {
  const WalkForwardResult(this.folds);
  final List<WalkForwardFold> folds;

  double get totalNetPnl =>
      folds.fold(0, (sum, fold) => sum + fold.testResult.netPnl);

  double get worstDrawdown => folds.isEmpty
      ? 0
      : folds
          .map((fold) => fold.testResult.maxDrawdownPercent)
          .reduce((a, b) => math.max(a, b).toDouble());

  int get totalTestTrades =>
      folds.fold(0, (sum, fold) => sum + fold.testResult.tradeCount);
}

class BacktestEngine {
  const BacktestEngine();

  BacktestResult run(
    List<MarketCandle> candles,
    BacktestConfig cfg, {
    int warmupBars = 25,
  }) {
    if (!cfg.startingBalance.isFinite ||
        cfg.startingBalance <= 0 ||
        cfg.feeRate < 0 ||
        cfg.slippageBps < 0 ||
        cfg.stopPercent <= 0 ||
        cfg.riskPercent <= 0 ||
        cfg.maxDrawdownPercent <= 0) {
      throw ArgumentError('Invalid backtest configuration.');
    }

    final data = candles.where((candle) => candle.isClosed).toList()
      ..sort((a, b) => a.timestamp.compareTo(b.timestamp));
    var balance = cfg.startingBalance;
    var peak = balance;
    var maxDrawdown = 0.0;
    var fees = 0.0;
    var winningPnl = 0.0;
    var losingPnl = 0.0;
    var halted = false;
    _Sim? position;
    final trades = <BacktestTrade>[];
    final equityCurve = <double>[balance];
    final firstTradeIndex = math.max(25, warmupBars).toInt();
    final slippage = cfg.slippageBps / 10000;

    for (var i = firstTradeIndex; i < data.length; i++) {
      final candle = data[i];

      if (position != null) {
        final stopPrice = position.effectiveStop;
        final stopHit = position.isLong
            ? candle.low <= stopPrice
            : candle.high >= stopPrice;
        final tp1Hit = position.isLong
            ? candle.high >= position.takeProfit1
            : candle.low <= position.takeProfit1;
        final tp2Hit = position.isLong
            ? candle.high >= position.takeProfit2
            : candle.low <= position.takeProfit2;

        // If SL and TP occur in the same OHLC candle, assume the adverse
        // event happened first. This avoids optimistic intrabar ordering.
        if (stopHit) {
          final trailingWasActive = position.trailingStop != null &&
              (position.isLong
                  ? position.trailingStop! > position.stop
                  : position.trailingStop! < position.stop);
          final fill = stopPrice *
              (position.isLong ? 1 - slippage : 1 + slippage);
          final closed = _close(
            position,
            fill,
            i,
            trailingWasActive ? 'TRAILING_STOP' : 'STOP_LOSS',
            cfg,
          );
          balance += closed.cashDelta;
          fees += closed.fees;
          trades.add(closed.trade);
          if (closed.net >= 0) {
            winningPnl += closed.net;
          } else {
            losingPnl -= closed.net;
          }
          position = null;
        } else {
          // TP1 is processed before TP2 if both levels were crossed in one
          // candle; the remaining half can then close at TP2.
          if (tp1Hit && !position.takeProfit1Hit) {
            final quantity = position.quantity * 0.5;
            final fill = position.takeProfit1 *
                (position.isLong ? 1 - slippage : 1 + slippage);
            final gross = (fill - position.entry) *
                quantity *
                (position.isLong ? 1 : -1);
            final fee = fill * quantity * cfg.feeRate;
            balance += gross - fee;
            fees += fee;
            position.quantity -= quantity;
            position.partialPnl += gross;
            position.partialFees += fee;
            position.takeProfit1Hit = true;
          }
          if (tp2Hit) {
            final fill = position.takeProfit2 *
                (position.isLong ? 1 - slippage : 1 + slippage);
            final closed = _close(
              position,
              fill,
              i,
              'TAKE_PROFIT_2',
              cfg,
            );
            balance += closed.cashDelta;
            fees += closed.fees;
            trades.add(closed.trade);
            if (closed.net >= 0) {
              winningPnl += closed.net;
            } else {
              losingPnl -= closed.net;
            }
            position = null;
          } else {
            position.updateTrailing(candle.high, candle.low, cfg.trailingStopPercent);
          }
        }
      } else if (!halted) {
        final prior = data
            .sublist(i - 25, i)
            .map((candle) => candle.close)
            .toList();
        final signal = calculateSignal(prices: prior);
        if (signal.confidence >= cfg.signalThreshold) {
          final isLong = signal.direction == 'LONG';
          final entry = candle.open * (isLong ? 1 + slippage : 1 - slippage);
          final plan = buildTradePlan(
            direction: signal.direction,
            entry: entry,
            capital: balance,
            riskPercent: cfg.riskPercent,
            leverage: 1,
            stopPercent: cfg.stopPercent,
            firstTargetR: cfg.firstTargetR,
            secondTargetR: cfg.secondTargetR,
          );
          final entryFee = entry * plan.quantity * cfg.feeRate;
          balance -= entryFee;
          fees += entryFee;
          position = _Sim(
            isLong: isLong,
            entry: entry,
            quantity: plan.quantity,
            stop: plan.stopLoss,
            takeProfit1: plan.takeProfit1,
            takeProfit2: plan.takeProfit2,
            entryFee: entryFee,
            entryIndex: i,
          );
        }
      }

      if (position != null) {
        final favourable = position.isLong ? candle.high : candle.low;
        final adverse = position.isLong ? candle.low : candle.high;
        final direction = position.isLong ? 1.0 : -1.0;
        final favourableEquity =
            balance + (favourable - position.entry) * position.quantity * direction;
        final adverseEquity =
            balance + (adverse - position.entry) * position.quantity * direction;
        peak = math.max(peak, favourableEquity).toDouble();
        final drawdown =
            peak <= 0 ? 0.0 : (peak - adverseEquity) / peak * 100;
        maxDrawdown = math.max(maxDrawdown, drawdown).toDouble();

        if (maxDrawdown >= cfg.maxDrawdownPercent) {
          halted = true;
          final fill = candle.close *
              (position.isLong ? 1 - slippage : 1 + slippage);
          final closed = _close(position, fill, i, 'MAX_DRAWDOWN', cfg);
          balance += closed.cashDelta;
          fees += closed.fees;
          trades.add(closed.trade);
          if (closed.net >= 0) {
            winningPnl += closed.net;
          } else {
            losingPnl -= closed.net;
          }
          position = null;
        }
      } else {
        peak = math.max(peak, balance).toDouble();
        final drawdown =
            peak <= 0 ? 0.0 : (peak - balance) / peak * 100;
        maxDrawdown = math.max(maxDrawdown, drawdown).toDouble();
        if (maxDrawdown >= cfg.maxDrawdownPercent) halted = true;
      }

      final markedEquity = balance +
          (position == null
              ? 0
              : (candle.close - position.entry) *
                  position.quantity *
                  (position.isLong ? 1 : -1));
      equityCurve.add(markedEquity);
    }

    if (position != null && data.isNotEmpty) {
      final last = data.last;
      final fill = last.close *
          (position.isLong ? 1 - slippage : 1 + slippage);
      final closed = _close(
        position,
        fill,
        data.length - 1,
        'END_OF_DATA',
        cfg,
      );
      balance += closed.cashDelta;
      fees += closed.fees;
      trades.add(closed.trade);
      if (closed.net >= 0) {
        winningPnl += closed.net;
      } else {
        losingPnl -= closed.net;
      }
      equityCurve.add(balance);
    }

    final net = balance - cfg.startingBalance;
    final buyHold = data.length < 2 || data.first.close <= 0
        ? 0.0
        : (data.last.close / data.first.close - 1) * 100;
    return BacktestResult(
      trades: List.unmodifiable(trades),
      finalBalance: balance,
      netPnl: net,
      returnPercent: net / cfg.startingBalance * 100,
      winRate: trades.isEmpty
          ? 0
          : trades.where((trade) => trade.netPnl > 0).length /
              trades.length *
              100,
      profitFactor: losingPnl == 0
          ? (winningPnl > 0 ? double.infinity : 0)
          : winningPnl / losingPnl,
      maxDrawdownPercent: maxDrawdown,
      equityCurve: List.unmodifiable(equityCurve),
      fees: fees,
      buyHoldReturnPercent: buyHold,
    );
  }

  WalkForwardResult walkForward(
    List<MarketCandle> candles, {
    int folds = 4,
    double trainFraction = 0.65,
    List<BacktestConfig>? candidates,
  }) {
    if (folds < 1 || trainFraction <= 0 || trainFraction >= 1) {
      throw ArgumentError('Invalid walk-forward split.');
    }
    final data = candles.where((candle) => candle.isClosed).toList()
      ..sort((a, b) => a.timestamp.compareTo(b.timestamp));
    final configs = candidates ?? defaultCandidates();
    final output = <WalkForwardFold>[];
    if (data.length < 150) return WalkForwardResult(const []);

    final firstTestStart = (data.length * trainFraction).floor();
    final remaining = data.length - firstTestStart;
    final testSize = (remaining / folds).floor();
    if (testSize < 25) return WalkForwardResult(const []);

    for (var fold = 0; fold < folds; fold++) {
      final testStart = firstTestStart + fold * testSize;
      final testEnd = fold == folds - 1
          ? data.length
          : math.min(data.length, testStart + testSize).toInt();
      if (testEnd - testStart < 25) continue;

      // Expanding window: every fold trains on all data available before
      // its test segment. Test candles never participate in optimization.
      final train = data.sublist(0, testStart);
      if (train.length < 80) continue;

      BacktestConfig? best;
      var bestScore = double.negativeInfinity;
      for (final candidate in configs) {
        final result = run(train, candidate);
        if (result.tradeCount == 0 ||
            result.maxDrawdownPercent > candidate.maxDrawdownPercent) {
          continue;
        }
        final score = result.netPnl -
            result.maxDrawdownPercent * candidate.startingBalance * 0.05;
        if (score > bestScore) {
          best = candidate;
          bestScore = score;
        }
      }
      if (best == null) continue;

      final warmup = train.skip(math.max(0, train.length - 25).toInt()).toList();
      final test = data.sublist(testStart, testEnd);
      final isolatedTest = <MarketCandle>[...warmup, ...test];
      final testResult = run(
        isolatedTest,
        best,
        warmupBars: warmup.length,
      );
      output.add(WalkForwardFold(
        0,
        testStart,
        testStart,
        testEnd,
        best,
        testResult,
      ));
    }
    return WalkForwardResult(List.unmodifiable(output));
  }

  List<BacktestConfig> defaultCandidates() {
    final output = <BacktestConfig>[];
    for (final stop in [0.5, 0.8, 1.0]) {
      for (final threshold in [55.0, 60.0, 65.0]) {
        for (final firstTarget in [1.0, 1.5]) {
          for (final secondTarget in [2.0, 2.5, 3.0]) {
            output.add(BacktestConfig(
              stopPercent: stop,
              signalThreshold: threshold,
              firstTargetR: firstTarget,
              secondTargetR: secondTarget,
            ));
          }
        }
      }
    }
    return output;
  }

  _Closed _close(
    _Sim position,
    double exit,
    int index,
    String reason,
    BacktestConfig cfg,
  ) {
    final raw = (exit - position.entry) *
        position.quantity *
        (position.isLong ? 1 : -1);
    final fee = exit * position.quantity * cfg.feeRate;
    final net =
        position.partialPnl + raw - position.entryFee - position.partialFees - fee;
    final trade = BacktestTrade(
      position.isLong ? 'LONG' : 'SHORT',
      position.entry,
      exit,
      net,
      reason,
      position.entryIndex,
      index,
    );
    return _Closed(trade, net, fee, raw - fee);
  }
}

class _Sim {
  _Sim({
    required this.isLong,
    required this.entry,
    required this.quantity,
    required this.stop,
    required this.takeProfit1,
    required this.takeProfit2,
    required this.entryFee,
    required this.entryIndex,
  }) : bestPrice = entry;

  final bool isLong;
  final double entry;
  double quantity;
  final double stop;
  final double takeProfit1;
  final double takeProfit2;
  final double entryFee;
  final int entryIndex;
  double partialPnl = 0;
  double partialFees = 0;
  bool takeProfit1Hit = false;
  double bestPrice;
  double? trailingStop;

  double get effectiveStop {
    final trailing = trailingStop;
    if (trailing == null) return stop;
    return isLong ? math.max(stop, trailing).toDouble() : math.min(stop, trailing).toDouble();
  }

  void updateTrailing(double high, double low, double trailingPercent) {
    if (trailingPercent <= 0) return;
    if (isLong) {
      bestPrice = math.max(bestPrice, high).toDouble();
      final candidate = bestPrice * (1 - trailingPercent / 100);
      trailingStop = trailingStop == null
          ? candidate
          : math.max(trailingStop!, candidate).toDouble();
    } else {
      bestPrice = math.min(bestPrice, low).toDouble();
      final candidate = bestPrice * (1 + trailingPercent / 100);
      trailingStop = trailingStop == null
          ? candidate
          : math.min(trailingStop!, candidate).toDouble();
    }
  }
}

class _Closed {
  const _Closed(this.trade, this.net, this.fees, this.cashDelta);
  final BacktestTrade trade;
  final double net;
  final double fees;
  final double cashDelta;
}
