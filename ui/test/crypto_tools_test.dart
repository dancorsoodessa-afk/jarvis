import 'package:flutter_test/flutter_test.dart';
import '../lib/crypto/crypto_tools.dart';

void main() {
  group('JarvisCrypto.indicators', () {
    test('calculates close, percentage change, moving averages and RSI', () {
      final candles = List<List<dynamic>>.generate(
        60,
        (index) => ['', '', '', '', (159 - index).toString()],
      );

      final values = JarvisCrypto.indicators(candles);

      expect(values['last'], 159);
      expect(values['change_pct'], closeTo(59, 0.0001));
      expect(values['sma20'], closeTo(149.5, 0.0001));
      expect(values['sma50'], closeTo(134.5, 0.0001));
      expect(values['rsi14'], 100);
    });

    test('returns null metrics for empty candles', () {
      final values = JarvisCrypto.indicators(const []);
      expect(values['last'], isNull);
      expect(values['change_pct'], isNull);
      expect(values['sma20'], isNull);
      expect(values['sma50'], isNull);
      expect(values['rsi14'], isNull);
    });
  });
}
