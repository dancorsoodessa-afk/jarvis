import 'package:flutter_test/flutter_test.dart';
import 'package:botok/market_scanner.dart';
import 'package:botok/okx_market.dart';

void main() {
  List<MarketCandle> candles({bool rising = true, int count = 80}) {
    var price = 100.0;
    return List.generate(count, (index) {
      final open = price;
      price *= rising ? 1.002 : 0.998;
      return MarketCandle(
        timestamp: DateTime.utc(2026).add(Duration(minutes: index)),
        open: open,
        high: (open > price ? open : price) * 1.001,
        low: (open < price ? open : price) * 0.999,
        close: price,
        volume: 1000,
      );
    });
  }

  MarketInstrument instrument(String id, double turnover, {String type = 'SWAP'}) =>
      MarketInstrument(
        id: id,
        base: id.split('-').first,
        quote: 'USDT',
        type: type,
        turnover: turnover,
        contractSize: type == 'SWAP' ? 0.01 : 0,
        lotSize: type == 'SWAP' ? 1 : 0.001,
        minSize: type == 'SWAP' ? 1 : 0.001,
        tickSize: 0.1,
        contractType: type == 'SWAP' ? 'linear' : '',
        spreadPercent: 0.03,
      );

  test('scanner chooses the highest-ranked aligned USDT swap candidate', () async {
    final scanner = MarketOpportunityScanner();
    final result = await scanner.scan(
      instruments: [instrument('AAA-USDT-SWAP', 1e7), instrument('BBB-USDT-SWAP', 5e7)],
      marketType: 'SWAP',
      loadCandles: (_, __, ___) async => candles(),
    );
    expect(result, isNotNull);
    expect(result!.instrument.id, 'BBB-USDT-SWAP');
    expect(result.analysis.isAligned, isTrue);
    expect(result.analysis.signal.direction, 'LONG');
  });

  test('scanner never returns SHORT for spot instruments', () async {
    final scanner = MarketOpportunityScanner();
    final result = await scanner.scan(
      instruments: [instrument('AAA-USDT', 1e7, type: 'SPOT')],
      marketType: 'SPOT',
      loadCandles: (_, __, ___) async => candles(rising: false),
    );
    expect(result, isNull);
  });

  test('scanner waits when multi-timeframe candle history is insufficient', () async {
    final scanner = MarketOpportunityScanner();
    final result = await scanner.scan(
      instruments: [instrument('AAA-USDT-SWAP', 1e7)],
      marketType: 'SWAP',
      loadCandles: (_, __, ___) async => candles(count: 10),
    );
    expect(result, isNull);
  });

  test('scanner rejects instruments without usable OKX size metadata', () async {
    final scanner = MarketOpportunityScanner();
    final result = await scanner.scan(
      instruments: [MarketInstrument(
        id: 'AAA-USDT-SWAP',
        base: 'AAA',
        quote: 'USDT',
        type: 'SWAP',
        turnover: 1e9,
      )],
      marketType: 'SWAP',
      loadCandles: (_, __, ___) async => candles(),
    );
    expect(result, isNull);
  });
}
