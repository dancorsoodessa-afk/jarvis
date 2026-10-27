import 'dart:convert';
import 'dart:io';

/// Public market-data toolkit. No API key is required for public endpoints.
/// Private account data and order execution are intentionally not exposed here.
class JarvisCrypto {
  static const _okx = 'https://www.okx.com';
  static Future<dynamic> _get(String url) async {
    final client = HttpClient();
    try {
      final request = await client.getUrl(Uri.parse(url)).timeout(const Duration(seconds: 12));
      request.headers.set('Accept', 'application/json');
      final response = await request.close().timeout(const Duration(seconds: 15));
      final body = await response.transform(utf8.decoder).join();
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw StateError('HTTP ${response.statusCode}: ${body.length > 180 ? body.substring(0, 180) : body}');
      }
      final parsed = jsonDecode(body);
      if (parsed is Map && parsed['code'] != null && parsed['code'].toString() != '0') {
        throw StateError(parsed['msg']?.toString() ?? 'Ошибка OKX');
      }
      return parsed;
    } finally {
      client.close(force: true);
    }
  }

  static Future<dynamic> _coinglass(String path, String apiKey) async {
    if (apiKey.trim().isEmpty) throw ArgumentError('Введите CoinGlass API key');
    final client = HttpClient();
    try {
      final uri = Uri.parse('https://open-api-v4.coinglass.com$path');
      final request = await client.getUrl(uri).timeout(const Duration(seconds: 12));
      request.headers.set('Accept', 'application/json');
      request.headers.set('CG-API-KEY', apiKey.trim());
      final response = await request.close().timeout(const Duration(seconds: 15));
      final body = await response.transform(utf8.decoder).join();
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw StateError('CoinGlass HTTP ${response.statusCode}: ${body.length > 180 ? body.substring(0, 180) : body}');
      }
      final parsed = jsonDecode(body);
      if (parsed is Map && parsed['code'] != null && parsed['code'].toString() != '0') {
        throw StateError('CoinGlass: ${parsed['msg'] ?? parsed['code']}');
      }
      return parsed is Map ? parsed['data'] : parsed;
    } finally {
      client.close(force: true);
    }
  }

  /// CoinGlass endpoints: futures liquidations, global long/short, aggregated CVD.
  static Future<Map<String, dynamic>> coinglassSnapshot({required String apiKey, String symbol = 'BTC', String interval = '1h'}) async {
    final encodedSymbol = Uri.encodeQueryComponent(symbol.toUpperCase());
    final encodedInterval = Uri.encodeQueryComponent(interval);
    final results = await Future.wait([
      _coinglass('/api/futures/liquidation/aggregated-history?symbol=$encodedSymbol&interval=$encodedInterval', apiKey),
      _coinglass('/api/futures/global-long-short-account-ratio/history?symbol=$encodedSymbol&interval=$encodedInterval', apiKey),
      _coinglass('/api/futures/aggregated-cvd/history?exchange_list=Binance,OKX,Bybit&symbol=$encodedSymbol&interval=$encodedInterval', apiKey),
      _coinglass('/api/futures/open-interest/aggregated-history?symbol=$encodedSymbol&interval=$encodedInterval', apiKey),
    ]);
    return {'liquidations': results[0], 'long_short': results[1], 'cvd': results[2], 'open_interest': results[3]};
  }

  /// Current OKX tickers: BTC, ETH and other requested spot instruments.
  static Future<List<Map<String, dynamic>>> tickers({List<String> symbols = const ['BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'XRP-USDT']}) async {
    final responses = await Future.wait(symbols.map((symbol) =>
      _get('$_okx/api/v5/market/ticker?instId=${Uri.encodeQueryComponent(symbol)}')
    ));
    final all = <Map<String, dynamic>>[];
    for (final data in responses) {
      if (data is Map && data['data'] is List) {
        for (final row in data['data']) {
          if (row is Map) all.add(Map<String, dynamic>.from(row));
        }
      }
    }
    return all;
  }

  /// OHLCV candles for supported OKX instruments/timeframes.
  static Future<List<List<dynamic>>> candles({String symbol = 'BTC-USDT', String timeframe = '1H', int limit = 100}) async {
    const allowed = {'1m','3m','5m','15m','30m','1H','2H','4H','6H','12H','1D','1W'};
    if (!allowed.contains(timeframe)) throw ArgumentError('Неподдерживаемый таймфрейм');
    final safeLimit = limit.clamp(1, 300);
    final data = await _get('$_okx/api/v5/market/candles?instId=${Uri.encodeQueryComponent(symbol)}&bar=$timeframe&limit=$safeLimit');
    if (data is Map && data['data'] is List) {
      return (data['data'] as List).whereType<List>().toList();
    }
    return const [];
  }

  /// Public perpetual swap funding rate and open interest.
  static Future<Map<String, dynamic>> derivatives({String symbol = 'BTC-USDT-SWAP'}) async {
    final encoded = Uri.encodeQueryComponent(symbol);
    final funding = await _get('$_okx/api/v5/public/funding-rate?instId=$encoded');
    final interest = await _get('$_okx/api/v5/public/open-interest?instType=SWAP&instId=$encoded');
    return {
      'funding': funding is Map && funding['data'] is List && (funding['data'] as List).isNotEmpty ? (funding['data'] as List).first : null,
      'open_interest': interest is Map && interest['data'] is List && (interest['data'] as List).isNotEmpty ? (interest['data'] as List).first : null,
    };
  }

  static double _close(List<dynamic> candle) => double.tryParse(candle.length > 4 ? candle[4].toString() : '') ?? 0;

  /// Transparent basic technical metrics calculated from candle closes.
  static Map<String, double?> indicators(List<List<dynamic>> candles) {
    final closes = candles.map(_close).where((v) => v > 0).toList().reversed.toList();
    if (closes.isEmpty) return {'last': null, 'change_pct': null, 'sma20': null, 'sma50': null, 'rsi14': null};
    double? sma(int period) => closes.length < period ? null : closes.skip(closes.length - period).reduce((a,b) => a+b) / period;
    double? rsi() {
      if (closes.length < 15) return null;
      var gains = 0.0, losses = 0.0;
      for (var i = closes.length - 14; i < closes.length; i++) {
        final diff = closes[i] - closes[i-1];
        if (diff > 0) gains += diff; else losses -= diff;
      }
      if (losses == 0) return 100;
      final rs = (gains / 14) / (losses / 14);
      return 100 - (100 / (1 + rs));
    }
    final first = closes.first;
    return {
      'last': closes.last,
      'change_pct': first == 0 ? null : (closes.last - first) / first * 100,
      'sma20': sma(20),
      'sma50': sma(50),
      'rsi14': rsi(),
    };
  }
}
