import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:web_socket_channel/web_socket_channel.dart';

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


class MarketCandle {
  const MarketCandle({
    required this.time,
    required this.open,
    required this.high,
    required this.low,
    required this.close,
    required this.volume,
    required this.confirmed,
  });

  final DateTime time;
  final double open;
  final double high;
  final double low;
  final double close;
  final double volume;
  final bool confirmed;

  factory MarketCandle.fromOkx(List<dynamic> row) => MarketCandle(
    time: DateTime.fromMillisecondsSinceEpoch(int.parse(row[0].toString()), isUtc: true),
    open: double.parse(row[1].toString()),
    high: double.parse(row[2].toString()),
    low: double.parse(row[3].toString()),
    close: double.parse(row[4].toString()),
    volume: double.tryParse(row[5].toString()) ?? 0,
    confirmed: row.length > 8 && row[8].toString() == '1',
  );
}

class OkxMarket {
  HttpClient? _http;
  WebSocketChannel? _socket;
  StreamSubscription<dynamic>? _subscription;
  Timer? _heartbeat;
  final _events = StreamController<Map<String, dynamic>>.broadcast();
  Stream<Map<String, dynamic>> get events => _events.stream;


  Future<List<MarketCandle>> loadCandles(
    String instrumentId, {
    String bar = '5m',
    int limit = 120,
  }) async {
    final client = _http ??= HttpClient();
    final uri = Uri.https('www.okx.com', '/api/v5/market/candles', {
      'instId': instrumentId,
      'bar': bar,
      'limit': limit.clamp(1, 300).toString(),
    });
    final request = await client.getUrl(uri).timeout(const Duration(seconds: 15));
    final response = await request.close().timeout(const Duration(seconds: 15));
    final body = await response.transform(utf8.decoder).join();
    if (response.statusCode != 200) {
      throw HttpException('OKX candles HTTP ${response.statusCode}');
    }
    final decoded = jsonDecode(body) as Map<String, dynamic>;
    if (decoded['code'] != '0') {
      throw FormatException('OKX candles: ${decoded['msg']}');
    }
    final rows = (decoded['data'] as List<dynamic>).cast<List<dynamic>>();
    return rows.map(MarketCandle.fromOkx).toList().reversed.toList();
  }

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

  Future<void> watch(String instrumentId) async {
    await disconnect();
    final socket = WebSocketChannel.connect(
      Uri.parse('wss://ws.okx.com:8443/ws/v5/public'),
    );
    _socket = socket;
    await socket.ready.timeout(const Duration(seconds: 12));
    socket.sink.add(jsonEncode({
      'op': 'subscribe',
      'args': [
        {'channel': 'tickers', 'instId': instrumentId},
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
