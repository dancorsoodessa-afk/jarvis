import 'package:flutter_test/flutter_test.dart';
import 'package:botok/signal_engine.dart';

void main() {
  List<double> rising() {
    var price = 100.0;
    return List.generate(80, (_) {
      price *= 1.001;
      return price;
    });
  }

  List<double> falling() {
    var price = 100.0;
    return List.generate(80, (_) {
      price *= 0.999;
      return price;
    });
  }

  test('seven timeframes combine into one aligned signal', () {
    final analysis = calculateMultiTimeframeAnalysis(
      pricesByTimeframe: {
        '1m': rising(),
        '3m': rising(),
        '5m': rising(),
        '15m': rising(),
        '1H': rising(),
        '1D': rising(),
        '1W': rising(),
      },
      bookImbalance: 0.4,
      tradeDelta: 0.3,
    );
    expect(analysis.activeTimeframes, 7);
    expect(analysis.signal.direction, 'LONG');
    expect(analysis.agreementPercent, 100);
    expect(analysis.isAligned, isTrue);
  });

  test('two active timeframes cannot authorize an entry', () {
    final analysis = calculateMultiTimeframeAnalysis(
      pricesByTimeframe: {
        '1m': rising(),
        '5m': rising(),
      },
    );
    expect(analysis.activeTimeframes, 2);
    expect(analysis.isAligned, isFalse);
  });

  test('higher timeframe weights participate in the unified score', () {
    final analysis = calculateMultiTimeframeAnalysis(
      pricesByTimeframe: {
        '1m': rising(),
        '3m': falling(),
        '5m': falling(),
        '15m': falling(),
        '1H': falling(),
        '1D': rising(),
        '1W': rising(),
      },
    );
    expect(analysis.activeTimeframes, 7);
    expect(analysis.agreementPercent, inInclusiveRange(0, 100));
    expect(analysis.signal.longProbability + analysis.signal.shortProbability,
        closeTo(100, 1e-8));
  });
}
