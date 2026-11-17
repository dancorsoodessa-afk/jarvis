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
    this.lastPrice = 0,
    this.spreadPercent = 0,
    this.contractSize = 0,
    this.lotSize = 0,
    this.minSize = 0,
    this.tickSize = 0,
    this.contractType = '',
    this.state = 'live',
  });

  final String id;
  final String base;
  final String quote;
  final String type;
  final double turnover;
  final double lastPrice;
  final double spreadPercent;
  final double contractSize;
  final double lotSize;
  final double minSize;
  final double tickSize;
  final String contractType;
  final String state;

  String get label => '$base/$quote';
}

class OkxMarket {
  HttpClient? _http;
  WebSocketChannel? _socket;
  WebSocketChannel? _businessSocket;
  StreamSubscription<dynamic>? _subscription;
  StreamSubscription<dynamic>? _businessSubscription;
  Timer? _heartbeat;
  Timer? _businessHeartbeat;
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
    final metadataUri = Uri.https('www.okx.com', '/api/v5/public/instruments', {'instType': kind});
    final metadataRequest = await client.getUrl(metadataUri).timeout(const Duration(seconds: 15));
    final metadataResponse = await metadataRequest.close().timeout(const Duration(seconds: 15));
    final metadataBody = await metadataResponse.transform(utf8.decoder).join();
    if (metadataResponse.statusCode != 200) {
      throw HttpException('OKX instrument metadata HTTP ${metadataResponse.statusCode}');
    }
    final metadataDecoded = jsonDecode(metadataBody) as Map<String, dynamic>;
    if (metadataDecoded['code'] != '0') {
      throw FormatException('OKX instrument metadata: ${metadataDecoded['msg']}');
    }
    final metadataRows = (metadataDecoded['data'] as List<dynamic>).cast<Map<String, dynamic>>();
    final metadataById = {for (final item in metadataRows) item['instId']?.toString() ?? '': item};
    double number(Map<String, dynamic> row, String key) =>
        double.tryParse(row[key]?.toString() ?? '') ?? 0;
    return rows.map((row) {
      final id = row['instId'] as String? ?? '';
      final parts = id.split('-');
      final base = parts.isNotEmpty ? parts[0] : id;
      final quote = parts.length > 1 ? parts[1] : '';
      final metadata = metadataById[id] ?? const <String, dynamic>{};
      final last = number(row, 'last');
      final bid = number(row, 'bidPx');
      final ask = number(row, 'askPx');
      final midpoint = (bid + ask) / 2;
      final rawTurnover = number(row, 'volCcy24h');
      final turnover = kind == 'SWAP' ? rawTurnover * last : rawTurnover;
      return MarketInstrument(
        id: id,
        base: base,
        quote: quote,
        type: kind,
        turnover: turnover,
        lastPrice: last,
        spreadPercent: bid > 0 && ask >= bid && midpoint > 0
            ? (ask - bid) / midpoint * 100
            : 100,
        contractSize: kind == 'SWAP' ? number(metadata, 'ctVal') : 0,
        lotSize: number(metadata, 'lotSz'),
        minSize: number(metadata, 'minSz'),
        tickSize: number(metadata, 'tickSz'),
        contractType: metadata['ctType']?.toString() ?? '',
        state: metadata['state']?.toString() ?? 'unknown',
      );
    }).where((item) => item.id.isNotEmpty && item.state == 'live').toList()
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

  void _listenSocket(WebSocketChannel socket, {required bool business}) {
    final subscription = socket.stream.listen((message) {
      if (message is! String) return;
      try {
        final decoded = jsonDecode(message);
        if (decoded is Map<String, dynamic>) {
          if (decoded['event'] == 'error') {
            _events.add({'type': 'error', 'message': decoded['msg'] ?? 'OKX WebSocket error', 'channel': business ? 'business' : 'public'});
          } else if (decoded['arg'] is Map && decoded['data'] is List) {
            _events.add({
              'type': decoded['arg']['channel'],
              'instId': decoded['arg']['instId'],
              'data': decoded['data'],
            });
          }
        }
      } catch (_) {
        // Ignore malformed frames; keep the live feed running.
      }
    }, onError: (Object error) {
      _events.add({'type': 'error', 'message': error.toString(), 'channel': business ? 'business' : 'public'});
    }, onDone: () {
      _events.add({'type': 'disconnected', 'channel': business ? 'business' : 'public'});
    });
    if (business) {
      _businessSubscription = subscription;
      _businessHeartbeat?.cancel();
      _businessHeartbeat = Timer.periodic(const Duration(seconds: 20), (_) {
        _businessSocket?.sink.add('ping');
      });
    } else {
      _subscription = subscription;
      _heartbeat?.cancel();
      _heartbeat = Timer.periodic(const Duration(seconds: 20), (_) {
        _socket?.sink.add('ping');
      });
    }
  }

  Future<void> watch(String instrumentId) async {
    await disconnect();
    final publicSocket = WebSocketChannel.connect(Uri.parse('wss://ws.okx.com/ws/v5/public'));
    _socket = publicSocket;
    await publicSocket.ready.timeout(const Duration(seconds: 12));
    final publicArgs = <Map<String, String>>[
      {'channel': 'tickers', 'instId': instrumentId},
      {'channel': 'books5', 'instId': instrumentId},
      {'channel': 'trades', 'instId': instrumentId},
      if (instrumentId.endsWith('-SWAP')) ...[
        {'channel': 'open-interest', 'instId': instrumentId},
        {'channel': 'funding-rate', 'instId': instrumentId},
        {'channel': 'liquidation-orders', 'instType': 'SWAP'},
      ],
    ];
    publicSocket.sink.add(jsonEncode({'op': 'subscribe', 'args': publicArgs}));
    _listenSocket(publicSocket, business: false);

    // OKX candle/K-line subscriptions belong to the business WebSocket endpoint.
    final businessSocket = WebSocketChannel.connect(Uri.parse('wss://ws.okx.com/ws/v5/business'));
    _businessSocket = businessSocket;
    await businessSocket.ready.timeout(const Duration(seconds: 12));
    businessSocket.sink.add(jsonEncode({
      'op': 'subscribe',
      'args': [
        ...['1m', '3m', '5m', '15m', '1H', '1D', '1W']
            .map((bar) => {'channel': 'candle$bar', 'instId': instrumentId}),
        if (instrumentId != 'BTC-USDT' && instrumentId != 'BTC-USDT-SWAP')
          {'channel': 'candle1m', 'instId': instrumentId.endsWith('-SWAP') ? 'BTC-USDT-SWAP' : 'BTC-USDT'},
      ],
    }));
    _listenSocket(businessSocket, business: true);
  }

  Future<void> disconnect() async {
    _heartbeat?.cancel();
    _heartbeat = null;
    _businessHeartbeat?.cancel();
    _businessHeartbeat = null;
    await _subscription?.cancel();
    _subscription = null;
    await _businessSubscription?.cancel();
    _businessSubscription = null;
    await _socket?.sink.close();
    _socket = null;
    await _businessSocket?.sink.close();
    _businessSocket = null;
  }

  Future<void> dispose() async {
    await disconnect();
    _http?.close(force: true);
    _http = null;
    await _events.close();
  }
}
