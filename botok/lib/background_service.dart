import 'dart:async';

import 'package:flutter_foreground_task/flutter_foreground_task.dart';

import 'okx_market.dart';
import 'paper_position.dart';
import 'signal_engine.dart';

@pragma('vm:entry-point')
void startBotokBackgroundService() {
  FlutterForegroundTask.setTaskHandler(BotokMarketTaskHandler());
}

/// On-device OKX feed and PAPER-only autonomous cycle.
/// No API keys or real order endpoints are used here.
class BotokMarketTaskHandler extends TaskHandler {
  OkxMarket? _market;
  StreamSubscription<Map<String, dynamic>>? _events;
  Timer? _reconnectTimer;
  Timer? _scanTimer;
  DateTime? _lastEventAt;
  String _instrumentId = 'BTC-USDT';
  String _marketType = 'SPOT';
  String _bar = '5m';
  int _retry = 0;
  bool _connecting = false;
  bool _scanning = false;
  bool _destroyed = false;
  bool _autoCycle = false;
  double _quoteBalance = 100;
  double _allocationPercent = 10;
  double _targetNetPercent = 1;
  double _feeRate = 0.001;
  double _paperBalance = 100;
  double _realizedPnl = 0;
  double _lastPrice = 0;
  double _bid = 0;
  double _ask = 0;
  double _bookImbalance = 0;
  double _tradeDelta = 0;
  PaperPosition? _position;
  final List<double> _prices = <double>[];

  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {
    final saved = await FlutterForegroundTask.getData(key: 'botok_config');
    if (saved is Map) _applyConfig(Map<String, dynamic>.from(saved));
    final savedPosition =
        await FlutterForegroundTask.getData(key: 'botok_paper_position');
    if (savedPosition is Map) {
      try {
        _position = PaperPosition.fromJson(
          Map<String, dynamic>.from(savedPosition),
        );
        _instrumentId = _position!.instrumentId;
      } catch (_) {
        _position = null;
        await FlutterForegroundTask.removeData(key: 'botok_paper_position');
      }
    }
    final savedAccounting =
        await FlutterForegroundTask.getData(key: 'botok_paper_accounting');
    if (savedAccounting is Map) {
      _paperBalance = _number(savedAccounting['balance'], _paperBalance);
      _realizedPnl = _number(savedAccounting['realizedPnl'], 0);
    } else {
      _paperBalance = _quoteBalance;
    }
    await _connect();
    if (_autoCycle && _position == null) _scheduleScan(const Duration(seconds: 2));
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
    final oldMarketType = _marketType;
    final oldBar = _bar;
    _applyConfig(config);
    unawaited(FlutterForegroundTask.saveData(
      key: 'botok_config',
      value: config,
    ));
    if (oldInstrument != _instrumentId ||
        oldMarketType != _marketType ||
        oldBar != _bar) {
      unawaited(_connect());
    }
    if (!_autoCycle) {
      _scanTimer?.cancel();
    } else if (_position == null) {
      _scheduleScan(const Duration(seconds: 1));
    }
    _sendStatus(_autoCycle ? 'auto_cycle_ready' : 'live');
  }

  double _number(Object? value, double fallback) {
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString() ?? '') ?? fallback;
  }

  void _applyConfig(Map<String, dynamic> config) {
    final id = config['instrumentId']?.toString().trim();
    if (id != null && id.isNotEmpty) _instrumentId = id;
    final type = config['marketType']?.toString().toUpperCase();
    if (type == 'SPOT' || type == 'SWAP') _marketType = type!;
    final bar = config['bar']?.toString();
    if (bar != null && bar.isNotEmpty) _bar = bar;
    _autoCycle = config['autoCycle'] == true;
    _quoteBalance = _number(config['quoteBalance'], _quoteBalance);
    _allocationPercent = _number(config['allocationPercent'], _allocationPercent);
    _targetNetPercent = _number(config['targetNetPercent'], _targetNetPercent);
    _feeRate = _number(config['feeRate'], _feeRate);
    if (_paperBalance <= 0) _paperBalance = _quoteBalance;
    if (_position == null && _realizedPnl == 0) {
      _paperBalance = _quoteBalance;
    }
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
        notificationTitle: 'BOTok • OKX ${_autoCycle ? 'AUTO PAPER' : 'мониторинг'}',
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
        final signal = calculateSignal(
          prices: _prices,
          bookImbalance: _bookImbalance,
          tradeDelta: _tradeDelta,
        );
        _managePosition(price);
        if (_autoCycle && _position == null && !_scanning) {
          _tryOpenPaper(price, signal);
        }
        _sendStatus('live', signal: signal);
        unawaited(FlutterForegroundTask.updateService(
          notificationTitle: 'BOTok • ${_autoCycle ? 'AUTO PAPER' : 'OKX LIVE'}',
          notificationText: _position == null
              ? '$_instrumentId • ${price.toStringAsFixed(6)}'
              : '${_position!.direction} $_instrumentId • SL ${_position!.stopLoss.toStringAsFixed(6)}',
        ));
      }
    } else if (type == 'books5') {
      final bids = row['bids'] as List? ?? const [];
      final asks = row['asks'] as List? ?? const [];
      double bidQty = 0;
      double askQty = 0;
      if (bids.isNotEmpty && bids.first is List) {
        _bid = double.tryParse((bids.first as List)[0].toString()) ?? 0;
      }
      if (asks.isNotEmpty && asks.first is List) {
        _ask = double.tryParse((asks.first as List)[0].toString()) ?? 0;
      }
      for (final level in bids) {
        if (level is List && level.length > 1) {
          bidQty += double.tryParse(level[1].toString()) ?? 0;
        }
      }
      for (final level in asks) {
        if (level is List && level.length > 1) {
          askQty += double.tryParse(level[1].toString()) ?? 0;
        }
      }
      final total = bidQty + askQty;
      _bookImbalance = total == 0 ? 0 : (bidQty - askQty) / total;
    } else if (type == 'trades') {
      final side = row['side']?.toString();
      final size = double.tryParse(row['sz']?.toString() ?? '') ?? 0;
      _tradeDelta = (_tradeDelta * 0.85 +
              (side == 'buy' ? 1 : -1) * (size / (size + 1)) * 0.15)
          .clamp(-1.0, 1.0)
          .toDouble();
    }
  }

  void _managePosition(double price) {
    final position = _position;
    if (position == null) return;
    final reason = position.exitReasonAt(price);
    if (reason == null) return;
    final pnl = position.netPnlAt(price);
    _paperBalance += pnl;
    _realizedPnl += pnl;
    _position = null;
    unawaited(FlutterForegroundTask.removeData(key: 'botok_paper_position'));
    unawaited(_saveAccounting());
    final label = reason == PaperExitReason.stopLoss ? 'STOP LOSS' : 'TAKE PROFIT';
    _sendStatus(
      'paper_closed',
      message: '$label • ${pnl >= 0 ? '+' : ''}${pnl.toStringAsFixed(4)} USDT net',
    );
    if (_autoCycle) _scheduleScan(const Duration(seconds: 3));
  }

  void _tryOpenPaper(double price, TradeSignal signal) {
    if (price <= 0 || signal.confidence < 60) return;
    if (_marketType == 'SPOT' && signal.direction != 'LONG') return;
    try {
      final plan = buildAllocationPlan(
        direction: signal.direction,
        entry: price,
        quoteBalance: _paperBalance,
        allocationPercent: _allocationPercent,
        targetNetPercent: _targetNetPercent,
        feeRate: _feeRate,
        leverage: 1,
      );
      _position = PaperPosition.fromPlan(
        plan,
        instrumentId: _instrumentId,
        feeRate: _feeRate,
      );
      unawaited(FlutterForegroundTask.saveData(
        key: 'botok_paper_position',
        value: _position!.toJson(),
      ));
      _sendStatus(
        'paper_opened',
        signal: signal,
        message: '${plan.direction} $_instrumentId • PAPER',
      );
    } catch (error) {
      _sendStatus('paper_plan_error', message: error.toString());
    }
  }

  Future<void> _scanMarket() async {
    if (_destroyed || !_autoCycle || _scanning || _position != null) return;
    _scanning = true;
    _sendStatus('scanning', message: 'Поиск ликвидных USDT-пар OKX');
    try {
      final instruments = await (_market ??= OkxMarket()).loadInstruments(_marketType);
      final candidates = instruments
          .where((item) =>
              item.quote == 'USDT' &&
              item.turnover > 0 &&
              (_marketType != 'SPOT' || !item.id.endsWith('-SWAP')))
          .take(20)
          .toList();
      MarketInstrument? best;
      var bestScore = 0.0;
      for (final instrument in candidates) {
        if (_destroyed || !_autoCycle || _position != null) break;
        try {
          final candles = await _market!.loadCandles(
            instrument.id,
            bar: _bar,
            limit: 80,
          );
          if (candles.length < 30) continue;
          final signal = calculateSignal(
            prices: candles.map((c) => c.close).toList(),
          );
          if (_marketType == 'SPOT' && signal.direction != 'LONG') continue;
          if (signal.confidence > bestScore) {
            bestScore = signal.confidence;
            best = instrument;
          }
        } catch (_) {
          // An unavailable pair must not stop the rest of the scan.
        }
      }
      if (best != null && bestScore >= 60 && _autoCycle && _position == null) {
        _instrumentId = best.id;
        _prices.clear();
        await _connect();
        _sendStatus(
          'candidate_selected',
          message: '${best.id} • ${bestScore.toStringAsFixed(1)}%',
        );
      } else if (_autoCycle && _position == null) {
        _scheduleScan(const Duration(seconds: 25));
        _sendStatus('no_opportunity', message: 'Нет сигнала выше 60%; повтор через 25 сек');
      }
    } catch (error) {
      _sendStatus('scan_error', message: error.toString());
      _scheduleScan(const Duration(seconds: 30));
    } finally {
      _scanning = false;
    }
  }

  void _scheduleScan(Duration delay) {
    if (_destroyed || !_autoCycle || _position != null) return;
    if (_scanTimer?.isActive == true) return;
    _scanTimer = Timer(delay, () {
      _scanTimer = null;
      unawaited(_scanMarket());
    });
  }

  Future<void> _saveAccounting() async {
    await FlutterForegroundTask.saveData(
      key: 'botok_paper_accounting',
      value: {
        'balance': _paperBalance,
        'realizedPnl': _realizedPnl,
      },
    );
  }

  Future<void> _healthCheck() async {
    if (_destroyed) return;
    final last = _lastEventAt;
    if (last == null ||
        DateTime.now().difference(last) > const Duration(seconds: 45)) {
      _scheduleReconnect();
    }
    if (_autoCycle && _position == null && !_scanning) {
      _scheduleScan(const Duration(seconds: 1));
    }
  }

  void _scheduleReconnect() {
    if (_destroyed || _reconnectTimer?.isActive == true) return;
    final exponent = _retry.clamp(0, 5).toInt();
    final seconds = (1 << exponent).clamp(1, 60).toInt();
    _retry = (_retry + 1).clamp(0, 6).toInt();
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
      'autoCycle': _autoCycle,
      'paperBalance': _paperBalance,
      'realizedPnl': _realizedPnl,
      'unrealizedPnl': _position?.netPnlAt(_lastPrice) ?? 0,
      'equity': _paperBalance + (_position?.netPnlAt(_lastPrice) ?? 0),
      'position': _position?.toJson(),
      'timestamp': DateTime.now().millisecondsSinceEpoch,
    });
  }

  @override
  Future<void> onDestroy(DateTime timestamp, bool isTimeout) async {
    _destroyed = true;
    _reconnectTimer?.cancel();
    _scanTimer?.cancel();
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
