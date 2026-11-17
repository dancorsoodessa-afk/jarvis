import 'package:flutter_test/flutter_test.dart';
import 'package:botok/trend_outlook.dart';

void main() {
  group('trend outlook', () {
    test('rising market produces bullish forecast and rising projected prices', () {
      final outlook = calculateTrendOutlook(
        List<double>.generate(60, (i) => 100 + i * 0.35),
      );
      expect(outlook.direction, 'BULLISH');
      expect(outlook.projectedPrices[0], greaterThan(outlook.lastPrice));
      expect(outlook.projectedPrices[1], greaterThan(outlook.projectedPrices[0]));
      expect(outlook.confidence, inInclusiveRange(0, 100));
    });

    test('falling market produces bearish forecast', () {
      final outlook = calculateTrendOutlook(
        List<double>.generate(60, (i) => 150 - i * 0.4),
      );
      expect(outlook.direction, 'BEARISH');
      expect(outlook.projectedPrices.last, lessThan(outlook.lastPrice));
    });

    test('insufficient or invalid prices return neutral forecast', () {
      final outlook = calculateTrendOutlook([100, 0, double.nan]);
      expect(outlook.direction, 'NEUTRAL');
      expect(outlook.projectedPrices, isEmpty);
    });
  });
}
