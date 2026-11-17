import 'dart:async';

import 'package:flutter_foreground_task/flutter_foreground_task.dart';

import 'okx_market.dart';
import 'signal_engine.dart';

@pragma('vm:entry-point')
void startBotokBackgroundService() {
  FlutterForegroundTask.setTaskHandler(BotokMarketTaskHandler());
}

/// Owns the public OKX feed in the foreground-service isolate.
/// It deliberately does not submit real orders.
class BotokMarketTaskHandler extends TaskHandler {
  OkxMarket? _market;
  StreamSubscription<Map<String, dynamic>>? _events;
  Timer? _reconnectTimer;
  DateTime? _lastEventAt;
  String _instrumentId = 'BTC-USDT';
  String _marketType = 'SPOT';
  int _retry = 0;
  bool _connecting = false;
  bool _destroyed = false;
  double _lastPrice = 0;
  double _bid = 0;
  double _ask = 0;
  final List<double> _prices = <double>[];

  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {
    final saved = await FlutterForegroundTask.getData(key: 'botok_config');
    if (saved is Map) {
      _applyConfig(Map<String, dynamic>.from(saved));
    }
    await _connect();
  }

  @override
  void onRepeatEvent(DateTime timestamp) {
    unawaited(_healthCheck());
  }

  @override
  void onReceiveData(Object data) {
    if (data is! Map) return;
    final config = Map<String, dynamic>.from(data);
    final oldInstrument = _instrumentId;
    _applyConfig(config);
    unawaited(FlutterForegroundTask.saveData(
      key: 'botok_config',
      value: config,
    ));
    if (oldInstrument != _instrumentId) {
      unawaited(_connect());
    }
  }

  void _applyConfig(Map<String, dynamic> config) {
    final id = config['instrumentId']?.toString().trim();
    if (id != null && id.isNotEmpty) _instrumentId = id;
    final type = config['marketType']?.toString().toUpperCase();
    if (type == 'SPOT' || type == 'SWAP') _marketType = type!;
  }

  Future<void> _connect() async {
    if (_connecting || _destroyed) return;
    _connecting = true;
    try {
      _market ??= OkxMarket();
      _events ??= _market!.events.listen(_handleEvent);
      await _market!.watch(_instrumentId);
      _retry = 0;
      _lastEventAt = DateTime.now();
      await FlutterForegroundTask.updateService(
        notificationTitle: 'BOTok • OKX мониторинг',
        notificationText: 'Подключено: $_instrumentId',
      );
      _sendStatus('connected');
    } catch (error) {
      _sendStatus('reconnect_error', message: error.toString());
      _scheduleReconnect();
    } finally {
      _connecting = false;
    }
  }

  void _handleEvent(Map<String, dynamic> event) {
    if (_destroyed) return;
    _lastEventAt = DateTime.now();
    final type = event['type']?.toString();
    if (type == 'error' || type == 'disconnected') {
      _sendStatus('reconnecting', message: event['message']?.toString());
      _scheduleReconnect();
      return;
    }
    final rows = event['data'];
    if (rows is! List || rows.isEmpty || rows.first is! Map) return;
    final row = Map<String, dynamic>.from(rows.first as Map);
    if (type == 'tickers') {
      final price = double.tryParse(row['last']?.toString() ?? '') ?? 0;
      if (price > 0) {
        _lastPrice = price;
        _prices.add(price);
        if (_prices.length > 160) _prices.removeAt(0);
        final signal = calculateSignal(prices: _prices);
        _sendStatus('live', signal: signal);
        unawaited(FlutterForegroundTask.updateService(
          notificationTitle: 'BOTok • OKX LIVE',
          notificationText: '$_instrumentId • ${price.toStringAsFixed(6)}',
        ));
      }
    } else if (type == 'books5') {
      final bids = row['bids'] as List? ?? const [];
      final asks = row['asks'] as List? ?? const [];
      if (bids.isNotEmpty && bids.first is List) {
        _bid = double.tryParse((bids.first as List).first.toString()) ?? 0;
      }
      if (asks.isNotEmpty && asks.first is List) {
        _ask = double.tryParse((asks.first as List).first.toString()) ?? 0;
      }
    }
  }

  Future<void> _healthCheck() async {
    if (_destroyed) return;
    final last = _lastEventAt;
    if (last == null ||
        DateTime.now().difference(last) > const Duration(seconds: 45)) {
      _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    if (_destroyed || _reconnectTimer?.isActive == true) return;
    final seconds = (1 << _retry.clamp(0, 5)).clamp(1, 60);
    _retry = (_retry + 1).clamp(0, 6);
    _reconnectTimer = Timer(Duration(seconds: seconds), () {
      _reconnectTimer = null;
      unawaited(_connect());
    });
  }

  void _sendStatus(String state, {String? message, TradeSignal? signal}) {
    FlutterForegroundTask.sendDataToMain({
      'state': state,
      'instrumentId': _instrumentId,
      'marketType': _marketType,
      'price': _lastPrice,
      'bid': _bid,
      'ask': _ask,
      'message': message ?? '',
      'longProbability': signal?.longProbability ?? 50.0,
      'shortProbability': signal?.shortProbability ?? 50.0,
      'rsi': signal?.rsi ?? 50.0,
      'timestamp': DateTime.now().millisecondsSinceEpoch,
    });
  }

  @override
  Future<void> onDestroy(DateTime timestamp, bool isTimeout) async {
    _destroyed = true;
    _reconnectTimer?.cancel();
    await _events?.cancel();
    await _market?.dispose();
    _events = null;
    _market = null;
  }

  @override
  void onNotificationButtonPressed(String id) {
    if (id == 'stop') {
      unawaited(FlutterForegroundTask.stopService());
    }
  }

  @override
  void onNotificationPressed() {
    FlutterForegroundTask.launchApp('/');
  }
}
