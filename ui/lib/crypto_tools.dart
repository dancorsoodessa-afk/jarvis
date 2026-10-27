import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

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

  /// Current OKX tickers: BTC, ETH and other requested spot instruments.
  static Future<List<Map<String, dynamic>>> tickers({List<String> symbols = const ['BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'XRP-USDT']}) async {
    final all = <Map<String, dynamic>>[];
    for (final symbol in symbols) {
      final data = await _get('$_okx/api/v5/market/ticker?instId=${Uri.encodeQueryComponent(symbol)}');
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

class JarvisCryptoScreen extends StatefulWidget {
  const JarvisCryptoScreen({super.key});
  @override
  State<JarvisCryptoScreen> createState() => _JarvisCryptoScreenState();
}

class _JarvisCryptoScreenState extends State<JarvisCryptoScreen> {
  bool _loading = false;
  String? _error;
  List<Map<String, dynamic>> _tickers = [];
  Map<String, dynamic> _derivatives = {};
  Map<String, double?> _indicators = {};
  String _symbol = 'BTC-USDT';
  String _timeframe = '1H';

  String _num(dynamic value, {int digits = 2}) {
    final n = double.tryParse(value?.toString() ?? '');
    if (n == null) return '—';
    return n.toStringAsFixed(digits);
  }

  Future<void> _refresh() async {
    setState(() { _loading = true; _error = null; });
    try {
      final results = await Future.wait([
        JarvisCrypto.tickers(),
        JarvisCrypto.candles(symbol: _symbol, timeframe: _timeframe),
        JarvisCrypto.derivatives(),
      ]);
      if (!mounted) return;
      setState(() {
        _tickers = (results[0] as List<Map<String, dynamic>>);
        _indicators = JarvisCrypto.indicators(results[1] as List<List<dynamic>>);
        _derivatives = results[2] as Map<String, dynamic>;
      });
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  void initState() { super.initState(); _refresh(); }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final funding = _derivatives['funding'] as Map?;
    final oi = _derivatives['open_interest'] as Map?;
    return Scaffold(
      appBar: AppBar(title: const Text('JARVIS · Криптоинструменты'), actions: [
        IconButton(tooltip: 'Обновить', onPressed: _loading ? null : _refresh, icon: const Icon(Icons.refresh)),
      ]),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        Text('РЫНОК · OKX', style: theme.textTheme.labelLarge?.copyWith(color: const Color(0xFF37D5EE), letterSpacing: 2)),
        const SizedBox(height: 8),
        if (_tickers.isEmpty && !_loading) const Text('Нажмите обновить, чтобы загрузить рыночные данные.'),
        ..._tickers.map((t) {
          final price = double.tryParse(t['last']?.toString() ?? '') ?? 0;
          final change = double.tryParse(t['sodUtc24h']?.toString() ?? '') ?? 0;
          return Card(child: ListTile(
            title: Text(t['instId']?.toString() ?? '—'),
            subtitle: Text('24 ч: ${_num(change)}'),
            trailing: Text('$ ${_num(price, digits: price < 1 ? 5 : 2)}', style: const TextStyle(fontWeight: FontWeight.bold)),
          ));
        }),
        const SizedBox(height: 16),
        Text('ТЕХНИЧЕСКИЙ АНАЛИЗ', style: theme.textTheme.labelLarge?.copyWith(color: const Color(0xFF37D5EE), letterSpacing: 1.5)),
        const SizedBox(height: 8),
        DropdownButtonFormField<String>(value: _symbol, decoration: const InputDecoration(labelText: 'Инструмент'), items: const [
          DropdownMenuItem(value: 'BTC-USDT', child: Text('BTC/USDT')),
          DropdownMenuItem(value: 'ETH-USDT', child: Text('ETH/USDT')),
          DropdownMenuItem(value: 'SOL-USDT', child: Text('SOL/USDT')),
        ], onChanged: (v) { if (v != null) setState(() => _symbol = v); }),
        DropdownButtonFormField<String>(value: _timeframe, decoration: const InputDecoration(labelText: 'Таймфрейм'), items: const [
          DropdownMenuItem(value: '15m', child: Text('15 минут')),
          DropdownMenuItem(value: '1H', child: Text('1 час')),
          DropdownMenuItem(value: '4H', child: Text('4 часа')),
          DropdownMenuItem(value: '1D', child: Text('1 день')),
        ], onChanged: (v) { if (v != null) setState(() => _timeframe = v); }),
        const SizedBox(height: 8),
        FilledButton.icon(onPressed: _loading ? null : _refresh, icon: const Icon(Icons.analytics_outlined), label: Text(_loading ? 'Загрузка…' : 'Обновить анализ')),
        ..._indicators.entries.map((e) => ListTile(title: Text(e.key), trailing: Text(_num(e.value)))),
        const SizedBox(height: 16),
        Text('ДЕРИВАТИВЫ', style: theme.textTheme.labelLarge?.copyWith(color: const Color(0xFF37D5EE), letterSpacing: 1.5)),
        ListTile(title: const Text('Funding rate'), trailing: Text(_num(funding?['fundingRate'], digits: 6))),
        ListTile(title: const Text('Open interest'), trailing: Text(_num(oi?['oi'] ?? oi?['oiCcy']))),
        const Text('Публичные данные. Сигналы не являются гарантией результата. Торговля и вывод средств из этого экрана не выполняются.', style: TextStyle(color: Colors.white60)),
        if (_error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text('Ошибка: $_error', style: const TextStyle(color: Colors.redAccent))),
      ]),
    );
  }
}
