import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:web_socket_channel/web_socket_channel.dart';


class MarketCandle {
  const MarketCandle({
    required this.timestamp,
    required this.open,
    required this.high,
    required this.low,
    required this.close,
    required this.volume,
    this.isClosed = true,
  });
  final DateTime timestamp;
  final double open;
  final double high;
  final double low;
  final double close;
  final double volume;
  final bool isClosed;

  factory MarketCandle.fromOkx(List<dynamic> row) => MarketCandle(
    timestamp: DateTime.fromMillisecondsSinceEpoch(int.parse(row[0].toString()), isUtc: true),
    open: double.parse(row[1].toString()),
    high: double.parse(row[2].toString()),
    low: double.parse(row[3].toString()),
    close: double.parse(row[4].toString()),
    volume: double.tryParse(row[5].toString()) ?? 0,
    isClosed: row.length <= 8 || row[8].toString() == '1',
  );
}

class MarketInstrument {
  const MarketInstrument({
    required this.id,
    required this.base,
    required this.quote,
    required this.type,
    required this.turnover,
  });

  final String id;
  final String base;
  final String quote;
  final String type;
  final double turnover;

  String get label => '$base/$quote';
}

class OkxMarket {
  HttpClient? _http;
  WebSocketChannel? _socket;
  StreamSubscription<dynamic>? _subscription;
  Timer? _heartbeat;
  final _events = StreamController<Map<String, dynamic>>.broadcast();
  Stream<Map<String, dynamic>> get events => _events.stream;

  Future<List<MarketInstrument>> loadInstruments(String type) async {
    final client = _http ??= HttpClient();
    final kind = type == 'SPOT' ? 'SPOT' : 'SWAP';
    final uri = Uri.https('www.okx.com', '/api/v5/market/tickers', {'instType': kind});
    final request = await client.getUrl(uri).timeout(const Duration(seconds: 15));
    final response = await request.close().timeout(const Duration(seconds: 15));
    final body = await response.transform(utf8.decoder).join();
    if (response.statusCode != 200) {
      throw HttpException('OKX HTTP ${response.statusCode}');
    }
    final decoded = jsonDecode(body) as Map<String, dynamic>;
    if (decoded['code'] != '0') throw FormatException('OKX: ${decoded['msg']}');
    final rows = (decoded['data'] as List<dynamic>).cast<Map<String, dynamic>>();
    return rows.map((row) {
      final id = row['instId'] as String? ?? '';
      final parts = id.split('-');
      final base = parts.isNotEmpty ? parts[0] : id;
      final quote = parts.length > 1 ? parts[1] : '';
      return MarketInstrument(
        id: id,
        base: base,
        quote: quote,
        type: kind,
        turnover: double.tryParse(row['volCcy24h']?.toString() ?? '') ?? 0,
      );
    }).where((item) => item.id.isNotEmpty).toList()
      ..sort((a, b) => b.turnover.compareTo(a.turnover));
  }


  Future<List<MarketCandle>> loadCandles(String instrumentId, {String bar = '1m', int limit = 100}) async {
    final client = _http ??= HttpClient();
    final safeLimit = limit.clamp(1, 300);
    final uri = Uri.https('www.okx.com', '/api/v5/market/candles', {
      'instId': instrumentId,
      'bar': bar,
      'limit': safeLimit.toString(),
    });
    final request = await client.getUrl(uri).timeout(const Duration(seconds: 15));
    final response = await request.close().timeout(const Duration(seconds: 15));
    final body = await response.transform(utf8.decoder).join();
    if (response.statusCode != 200) throw HttpException('OKX candles HTTP ${response.statusCode}');
    final decoded = jsonDecode(body) as Map<String, dynamic>;
    if (decoded['code'] != '0') throw FormatException('OKX candles: ${decoded['msg']}');
    final rows = decoded['data'] as List<dynamic>;
    return rows.map((row) => MarketCandle.fromOkx(row as List<dynamic>)).toList()
      ..sort((a, b) => a.timestamp.compareTo(b.timestamp));
  }

  Future<List<MarketCandle>> loadHistory(
    String instrumentId, {
    String bar = '1m',
    int limit = 1200,
  }) async {
    final target = limit.clamp(1, 1500).toInt();
    final collected = <int, MarketCandle>{};
    String? after;
    var pages = 0;
    while (collected.length < target && pages < 5) {
      final remaining = target - collected.length;
      final pageLimit = remaining.clamp(1, 300).toInt();
      final query = <String, String>{
        'instId': instrumentId,
        'bar': bar,
        'limit': pageLimit.toString(),
        if (after != null) 'after': after,
      };
      final client = _http ??= HttpClient();
      final request = await client
          .getUrl(Uri.https('www.okx.com', '/api/v5/market/history-candles', query))
          .timeout(const Duration(seconds: 15));
      final response = await request.close().timeout(const Duration(seconds: 15));
      final body = await response.transform(utf8.decoder).join();
      if (response.statusCode != 200) {
        throw HttpException('OKX history candles HTTP ${response.statusCode}');
      }
      final decoded = jsonDecode(body) as Map<String, dynamic>;
      if (decoded['code'] != '0') {
        throw FormatException('OKX history candles: ${decoded['msg']}');
      }
      final rows = (decoded['data'] as List<dynamic>);
      if (rows.isEmpty) break;
      var oldest = 0;
      for (final raw in rows) {
        final row = raw as List<dynamic>;
        final candle = MarketCandle.fromOkx(row);
        collected[candle.timestamp.millisecondsSinceEpoch] = candle;
        final timestamp = int.parse(row[0].toString());
        if (oldest == 0 || timestamp < oldest) oldest = timestamp;
      }
      if (oldest == 0 || after == oldest.toString() || rows.length < pageLimit) break;
      after = oldest.toString();
      pages++;
      await Future<void>.delayed(const Duration(milliseconds: 120));
    }
    final result = collected.values.toList()
      ..sort((a, b) => a.timestamp.compareTo(b.timestamp));
    return result.length > target ? result.sublist(result.length - target) : result;
  }

  Future<void> watch(String instrumentId) async {
    await disconnect();
    final socket = WebSocketChannel.connect(
      Uri.parse('wss://ws.okx.com/ws/v5/public'),
    );
    _socket = socket;
    await socket.ready.timeout(const Duration(seconds: 12));
    socket.sink.add(jsonEncode({
      'op': 'subscribe',
      'args': [
        {'channel': 'tickers', 'instId': instrumentId},
        ...['1m', '3m', '5m', '15m', '1H', '1D', '1W'].map((bar) => {'channel': 'candle$bar', 'instId': instrumentId}),
        {'channel': 'books5', 'instId': instrumentId},
        {'channel': 'trades', 'instId': instrumentId},
      ],
    }));
    _subscription = socket.stream.listen((message) {
      if (message is! String) return;
      try {
        final decoded = jsonDecode(message);
        if (decoded is Map<String, dynamic>) {
          if (decoded['event'] == 'error') {
            _events.add({'type': 'error', 'message': decoded['msg'] ?? 'WebSocket error'});
          } else if (decoded['arg'] is Map && decoded['data'] is List) {
            _events.add({
              'type': decoded['arg']['channel'],
              'data': decoded['data'],
            });
          }
        }
      } catch (_) {
        // Ignore malformed public-feed frames; the next valid frame continues the stream.
      }
    }, onError: (Object error) {
      _events.add({'type': 'error', 'message': error.toString()});
    }, onDone: () {
      _events.add({'type': 'disconnected'});
    });
    _heartbeat?.cancel();
    _heartbeat = Timer.periodic(const Duration(seconds: 20), (_) {
      socket.sink.add('ping');
    });
  }

  Future<void> disconnect() async {
    _heartbeat?.cancel();
    _heartbeat = null;
    await _subscription?.cancel();
    _subscription = null;
    await _socket?.sink.close();
    _socket = null;
  }

  Future<void> dispose() async {
    await disconnect();
    _http?.close(force: true);
    _http = null;
    await _events.close();
  }
}
