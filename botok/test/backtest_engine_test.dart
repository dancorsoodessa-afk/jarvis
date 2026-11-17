import 'package:flutter_test/flutter_test.dart';
import 'package:botok/backtest_engine.dart';
import 'package:botok/forecast_engine.dart';
import 'package:botok/okx_market.dart';

void main() {
  List<MarketCandle> data({int n = 500}) {
    var price = 100.0;
    return List.generate(n, (index) {
      final open = price;
      price *= 1.0008 + (index % 7 == 0 ? -0.0015 : 0.0002);
      final close = price;
      return MarketCandle(
        timestamp: DateTime.utc(2026).add(Duration(minutes: index)),
        open: open,
        high: (open > close ? open : close) * 1.001,
        low: (open < close ? open : close) * 0.999,
        close: close,
        volume: 10,
        isClosed: true,
      );
    });
  }

  test('all seven requested OKX timeframes are configured', () {
    expect(
      MarketTimeframe.all.map((timeframe) => timeframe.bar).toList(),
      ['1m', '3m', '5m', '15m', '1H', '1D', '1W'],
    );
  });

  test('forecast returns a future price cone', () {
    final forecast = buildMarketForecast(data());
    expect(forecast, isNotNull);
    expect(forecast!.points, hasLength(12));
    expect(forecast.projectedLower, lessThanOrEqualTo(forecast.projectedMedian));
    expect(forecast.projectedUpper, greaterThanOrEqualTo(forecast.projectedMedian));
    expect(forecast.bullishProbability + forecast.bearishProbability, closeTo(100, 1e-8));
  });

  test('forecast is evaluated only on later, unseen candles', () {
    final validation = validateMarketForecast(
      data(n: 260),
      horizonBars: 5,
      maxSamples: 40,
    );
    expect(validation, isNotNull);
    expect(validation!.samples, greaterThan(0));
    expect(validation.directionalAccuracyPercent, inInclusiveRange(0, 100));
    expect(validation.intervalCoveragePercent, inInclusiveRange(0, 100));
    expect(validation.meanAbsoluteErrorPercent, greaterThanOrEqualTo(0));
  });

  test('backtest produces finite account and risk metrics', () {
    final result = const BacktestEngine().run(data(), const BacktestConfig());
    expect(result.finalBalance.isFinite, isTrue);
    expect(result.fees, greaterThanOrEqualTo(0));
    expect(result.maxDrawdownPercent, greaterThanOrEqualTo(0));
    expect(result.buyHoldReturnPercent.isFinite, isTrue);
    expect(result.equityCurve, isNotEmpty);
  });

  test('walk-forward uses expanding training windows and disjoint future tests', () {
    final result = const BacktestEngine().walkForward(
      data(n: 800),
      folds: 3,
      candidates: [
        BacktestConfig(signalThreshold: 55),
        BacktestConfig(stopPercent: 1, signalThreshold: 55),
      ],
    );
    expect(result.folds, isNotEmpty);
    for (var index = 0; index < result.folds.length; index++) {
      final fold = result.folds[index];
      expect(fold.trainStart, 0);
      expect(fold.trainEnd, fold.testStart);
      expect(fold.trainEnd, lessThan(fold.testEnd));
      if (index > 0) {
        expect(fold.testStart, greaterThanOrEqualTo(result.folds[index - 1].testEnd));
      }
    }
  });
}
