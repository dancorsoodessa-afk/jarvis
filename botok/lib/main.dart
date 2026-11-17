import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter_background_service/flutter_background_service.dart';

import 'okx_market.dart';
import 'paper_trading.dart';
import 'forecast_engine.dart';
import 'backtest_engine.dart';
import 'signal_engine.dart';
import 'paper_guard_service.dart';
import 'market_scanner.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializePaperGuardService();
  runApp(const BotokApp());
}

const _bg = Color(0xFF080D18);
const _panel = Color(0xFF111B2C);
const _muted = Color(0xFF8292AA);
const _green = Color(0xFF22D3A6);
const _red = Color(0xFFFF647C);
const _blue = Color(0xFF65A7FF);

class BotokApp extends StatelessWidget {
  const BotokApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'BOTok',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: _bg,
      colorScheme: const ColorScheme.dark(primary: _blue, surface: _panel),
      useMaterial3: true,
      snackBarTheme: const SnackBarThemeData(behavior: SnackBarBehavior.floating, backgroundColor: Color(0xFF1B2940), contentTextStyle: TextStyle(color: Colors.white, fontSize: 13), insetPadding: EdgeInsets.fromLTRB(16, 0, 16, 18)),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: _panel,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide.none),
      ),
    ),
    home: const DashboardPage(),
  );
}

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key});
  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  final _market = OkxMarket();
  final _candles = <MarketCandle>[];
  final Map<String, List<MarketCandle>> _candlesByTimeframe = {};
  final List<MarketCandle> _btcCandles = [];
  String _selectedTimeframe = '1m';
  BacktestResult? _backtestResult;
  WalkForwardResult? _walkForwardResult;
  final _search = TextEditingController();
  final _perTradeMargin = TextEditingController(text: '10');
  final _autoProfitTarget = TextEditingController(text: '5');
  StreamSubscription<Map<String, dynamic>>? _feed;
  StreamSubscription<Map<String, dynamic>?>? _guardFeed;
  StreamSubscription<Map<String, dynamic>?>? _guardStatusFeed;
  StreamSubscription<Map<String, dynamic>?>? _guardErrorFeed;
  StreamSubscription<Map<String, dynamic>?>? _guardStoppedFeed;
  String _guardStatus = 'не запущен';
  bool _guardRunning = false;
  DateTime _lastGuardCheck = DateTime.fromMillisecondsSinceEpoch(0);
  List<MarketInstrument> _instruments = [];
  MarketInstrument? _selected;
  String _marketType = 'SPOT';
  String _status = 'Загрузка рынка OKX…';
  double _price = 0;
  double _bid = 0;
  double _ask = 0;
  double _bookImbalance = 0;
  double _tradeDelta = 0;
  double _fundingRate = 0;
  double _openInterestUsd = 0;
  double _openInterestChangePercent = 0;
  int _recentLiquidationEvents = 0;
  double _longLiquidationContracts = 0;
  double _shortLiquidationContracts = 0;
  double _leverage = 1;
  double _riskPercent = 1;
  late PaperTradingEngine _paper;
  Future<void>? _paperRestore;
  bool _paperReady = false;
  DateTime _lastPaperPersist = DateTime.fromMillisecondsSinceEpoch(0);
  String _positionState = 'Нет открытой paper-позиции';
  bool _loading = false;
  bool _confirmMode = true;
  bool _autoProfitEnabled = false;
  bool _autoEntryInProgress = false;
  bool _autoScanBusy = false;
  String _autoScanStatus = 'Ожидание запуска';
  final _scanner = const MarketOpportunityScanner();
  Timer? _autoScanTimer;
  Future<void>? _autoSettingsRestore;
  DateTime _lastAutoEntryAt = DateTime.fromMillisecondsSinceEpoch(0);
  Timer? _reconnectTimer;

  MultiTimeframeAnalysis get _analysis => calculateMultiTimeframeAnalysis(
    pricesByTimeframe: _candlesByTimeframe.map(
      (bar, candles) => MapEntry(bar, candles.map((candle) => candle.close).toList()),
    ),
    candlesByTimeframe: _candlesByTimeframe,
    bookImbalance: _bookImbalance,
    tradeDelta: _tradeDelta,
    fundingRate: _fundingRate,
    openInterestChangePercent: _openInterestChangePercent,
  );

  List<MarketInstrument> get _filtered {
    final q = _search.text.trim().toUpperCase();
    if (q.isEmpty) return _instruments.take(120).toList();
    return _instruments.where((i) => i.id.toUpperCase().contains(q)).take(80).toList();
  }

  @override
  void initState() {
    super.initState();
    _paper = PaperTradingEngine(initialBalance: 1000);
    _paperRestore = _restorePaper();
    _autoSettingsRestore = _restoreAutoSettings();
    _guardFeed = FlutterBackgroundService().on('paperUpdate').listen((event) {
      if (!mounted || event == null) return;
      final wallet = event['wallet'];
      if (wallet is! String) return;
      try {
        _paper = PaperTradingEngine.decode(wallet);
        if (event['autoOpened'] == true) _lastAutoEntryAt = DateTime.now();
        final price = double.tryParse(event['price']?.toString() ?? '') ?? 0;
        if (price > 0) _price = price;
        final reason = event['closedReason'];
        _guardRunning = reason is! String || reason.isEmpty || _autoProfitEnabled;
        if (reason is String && reason.isNotEmpty) {
          _positionState = 'PAPER закрыта фоновым контроллером: $reason';
          _guardStatus = _autoProfitEnabled
              ? 'позиция закрыта • автопоиск следующей сделки'
              : 'позиция закрыта';
          if (!_autoProfitEnabled) stopPaperGuardService();
        }
        setState(() {});
      } catch (error) {
        _guardStatus = 'ошибка синхронизации';
        _positionState = 'Ошибка синхронизации фонового PAPER: $error';
        setState(() {});
      }
    });
    _guardStatusFeed = FlutterBackgroundService().on('guardStatus').listen((event) {
      if (!mounted || event == null) return;
      setState(() => _guardStatus = event['status']?.toString() ?? _guardStatus);
    });
    _guardErrorFeed = FlutterBackgroundService().on('guardError').listen((event) {
      if (!mounted || event == null) return;
      setState(() => _guardStatus = event['message']?.toString() ?? 'ошибка');
    });
    _guardStoppedFeed = FlutterBackgroundService().on('guardStopped').listen((_) {
      _guardRunning = false;
      if (mounted) setState(() => _guardStatus = 'не активен');
    });
    _loadMarket();
    _search.addListener(() { if (mounted) setState(() {}); });
  }

  Future<void> _restorePaper() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = prefs.getString(paperWalletPreferenceKey);
      if (saved != null) _paper = PaperTradingEngine.decode(saved);
      if (_paper.openPosition != null) {
        _positionState = 'PAPER ${_paper.openPosition!.plan.direction} восстановлена • SL/TP активны';
      }
    } catch (e) {
      _positionState = 'Не удалось восстановить демо-кошелёк: $e';
    }
    if (mounted) setState(() => _paperReady = true);
    if (_paper.openPosition != null) {
      _guardStatus = 'восстановление мониторинга';
      try {
        await startPaperGuardService();
        _guardRunning = await FlutterBackgroundService().isRunning();
        if (!_guardRunning) _guardStatus = 'фоновая защита не подтверждена';
      } catch (error) {
        _guardRunning = false;
        _guardStatus = 'ошибка восстановления: $error';
      }
    }
  }

  Future<void> _persistPaper() async {
    _lastPaperPersist = DateTime.now();
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(paperWalletPreferenceKey, _paper.encode());
    } catch (e) {
      if (mounted) _toast('Ошибка сохранения демо-кошелька: $e');
    }
  }

  Future<void> _loadMarket() async {
    await _paperRestore;
    await _autoSettingsRestore;
    if (!mounted) return;
    final savedPosition = _paper.openPosition;
    if (savedPosition != null) {
      _marketType = savedPosition.instrumentId.endsWith('-SWAP') ? 'SWAP' : 'SPOT';
    }
    setState(() { _loading = true; _status = 'Получаем инструменты OKX…'; });
    try {
      final items = await _market.loadInstruments(_marketType);
      if (savedPosition != null && !items.any((item) => item.id == savedPosition.instrumentId)) {
        throw StateError('Открытая PAPER-позиция сохранена для ${savedPosition.instrumentId}, но инструмент не найден. Позиция оставлена без изменений.');
      }
      if (!mounted) return;
      setState(() {
        _instruments = items;
        final wantedInstrument = _paper.openPosition?.instrumentId ?? (_marketType == 'SPOT' ? 'BTC-USDT' : 'BTC-USDT-SWAP');
        _selected = items.firstWhere(
          (i) => i.id == wantedInstrument,
          orElse: () => items.isNotEmpty ? items.first : throw StateError('OKX returned no instruments'),
        );
        _bid = _selected!.bidPrice;
        _ask = _selected!.askPrice;
        _status = 'OKX: ${items.length} инструментов загружено';
      });
      await _connectSelected();
    } catch (e) {
      if (mounted) setState(() => _status = 'Ошибка загрузки OKX: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _connectSelected() async {
    final instrument = _selected;
    if (instrument == null) return;
    await _feed?.cancel();
    try {
      final loaded = await Future.wait(MarketTimeframe.all.map((tf) => _market.loadCandles(instrument.id, bar: tf.bar, limit: 300).then((items) => MapEntry(tf.bar, items))));
      _candlesByTimeframe..clear()..addEntries(loaded.map((entry) => MapEntry(entry.key, entry.value)));
      final selectedHistory = await _market.loadHistory(instrument.id, bar: _selectedTimeframe, limit: 1200);
      if (selectedHistory.isNotEmpty) _candlesByTimeframe[_selectedTimeframe] = selectedHistory;
      _candles..clear()..addAll(_candlesByTimeframe[_selectedTimeframe] ?? const []);
      final oneMinute = _candlesByTimeframe['1m'] ?? const <MarketCandle>[];
      if (oneMinute.isNotEmpty) _price = oneMinute.last.close;
      _bid = instrument.bidPrice;
      _ask = instrument.askPrice;
      _btcCandles.clear();
      final benchmarkId = instrument.id.endsWith('-SWAP') ? 'BTC-USDT-SWAP' : 'BTC-USDT';
      if (instrument.id != benchmarkId) {
        try { _btcCandles.addAll(await _market.loadCandles(benchmarkId, bar: '1m', limit: 300)); } catch (_) {}
      }
    } catch (e) {
      if (mounted) setState(() => _status = 'Свечной архив OKX недоступен: $e');
    }
    _bookImbalance = 0;
    _tradeDelta = 0;
    _fundingRate = 0;
    _openInterestUsd = 0;
    _openInterestChangePercent = 0;
    _recentLiquidationEvents = 0;
    _longLiquidationContracts = 0;
    _shortLiquidationContracts = 0;
    await _market.watch(instrument.id);
    _feed = _market.events.listen(_onMarketEvent);
    if (mounted) setState(() => _status = 'LIVE • ${instrument.id}');
  }

  void _onMarketEvent(Map<String, dynamic> event) {
    if (!mounted) return;
    final type = event['type'];
    final rows = event['data'];
    if (type == 'error') {
      setState(() => _status = 'Поток OKX: ${event['message']}');
      return;
    }
    if (type == 'disconnected') {
      setState(() => _status = 'Поток OKX отключён — переподключение…');
      _scheduleReconnect();
      return;
    }
    if (rows is! List || rows.isEmpty) return;
    if (type is String && type.startsWith('candle')) {
      final bar = type.substring(6);
      final eventInstrument = event['instId']?.toString();
      if (bar == '1m' && eventInstrument != null && eventInstrument != _selected?.id && eventInstrument.startsWith('BTC-')) {
        for (final raw in rows) {
          try {
            final candle = MarketCandle.fromOkx(raw as List<dynamic>);
            final index = _btcCandles.indexWhere((item) => item.timestamp == candle.timestamp);
            if (index >= 0) { _btcCandles[index] = candle; } else { _btcCandles.add(candle); if (_btcCandles.length > 500) _btcCandles.removeAt(0); }
          } catch (_) {}
        }
        setState(() {});
        return;
      }
      final series = _candlesByTimeframe.putIfAbsent(bar, () => <MarketCandle>[]);
      for (final raw in rows) {
        try {
          final candle = MarketCandle.fromOkx(raw as List<dynamic>);
          final index = series.indexWhere((item) => item.timestamp == candle.timestamp);
          if (index >= 0) { series[index] = candle; } else { series.add(candle); if (series.length > 1500) series.removeAt(0); }
        } catch (_) {}
      }
      if (bar == _selectedTimeframe) { _candles..clear()..addAll(series); }
      setState(() {});
      return;
    }
    final row = rows.first as Map<String, dynamic>;
    if (type == 'tickers') {
      final last = double.tryParse(row['last']?.toString() ?? '') ?? 0;
      final bid = double.tryParse(row['bidPx']?.toString() ?? '') ?? 0;
      final ask = double.tryParse(row['askPx']?.toString() ?? '') ?? 0;
      if (bid > 0) _bid = bid;
      if (ask > 0) _ask = ask;
      if (last > 0) {
        _price = last;
        final position = _paper.openPosition;
        if (position != null) {
          final executableMark = position.isLong ? (_bid > 0 ? _bid : last) : (_ask > 0 ? _ask : last);
          _checkPaperGuard(executableMark);
        }
      }
    } else if (type == 'books5') {
      final bids = (row['bids'] as List<dynamic>? ?? []);
      final asks = (row['asks'] as List<dynamic>? ?? []);
      double bidQty = 0, askQty = 0;
      if (bids.isNotEmpty) {
        _bid = double.tryParse((bids.first as List)[0].toString()) ?? 0;
      }
      if (asks.isNotEmpty) {
        _ask = double.tryParse((asks.first as List)[0].toString()) ?? 0;
      }
      for (final level in bids) { bidQty += double.tryParse((level as List)[1].toString()) ?? 0; }
      for (final level in asks) { askQty += double.tryParse((level as List)[1].toString()) ?? 0; }
      final total = bidQty + askQty;
      _bookImbalance = total == 0 ? 0 : (bidQty - askQty) / total;
    } else if (type == 'trades') {
      final side = row['side']?.toString();
      final size = double.tryParse(row['sz']?.toString() ?? '') ?? 0;
      _tradeDelta = (_tradeDelta * 0.85 + (side == 'buy' ? 1 : -1) * (size / (size + 1)) * 0.15).clamp(-1.0, 1.0).toDouble();
    } else if (type == 'funding-rate') {
      _fundingRate = double.tryParse(row['fundingRate']?.toString() ?? '') ?? _fundingRate;
    } else if (type == 'open-interest') {
      final nextOi = double.tryParse(row['oiUsd']?.toString() ?? '') ?? 0;
      if (nextOi > 0 && _openInterestUsd > 0) {
        _openInterestChangePercent = ((nextOi - _openInterestUsd) / _openInterestUsd * 100).clamp(-20.0, 20.0).toDouble();
      }
      if (nextOi > 0) _openInterestUsd = nextOi;
    } else if (type == 'liquidation-orders') {
      var events = 0;
      var longContracts = 0.0;
      var shortContracts = 0.0;
      for (final item in rows) {
        if (item is! Map<String, dynamic> || item['instId'] != _selected?.id) continue;
        final details = item['details'];
        if (details is! List) continue;
        for (final detail in details) {
          if (detail is! Map<String, dynamic>) continue;
          final size = double.tryParse(detail['sz']?.toString() ?? '') ?? 0;
          events++;
          if (detail['posSide'] == 'long') longContracts += size;
          if (detail['posSide'] == 'short') shortContracts += size;
        }
      }
      _recentLiquidationEvents = events;
      _longLiquidationContracts = longContracts;
      _shortLiquidationContracts = shortContracts;
    }
    setState(() {});
  }

  void _scheduleReconnect() {
    if (_reconnectTimer?.isActive == true || _selected == null || !mounted) return;
    _reconnectTimer = Timer(const Duration(seconds: 3), () {
      if (mounted && !_loading && _selected != null) _connectSelected();
    });
  }

  Future<void> _setTimeframe(String bar) async {
    if (bar == _selectedTimeframe) return;
    setState(() { _selectedTimeframe = bar; _candles..clear()..addAll(_candlesByTimeframe[bar] ?? const []); _backtestResult = null; _walkForwardResult = null; });
    if (_selected != null) {
      try {
        final history = await _market.loadHistory(_selected!.id, bar: bar, limit: 1200);
        if (history.isNotEmpty) _candlesByTimeframe[bar] = history;
        if (mounted) setState(() => _candles..clear()..addAll(_candlesByTimeframe[bar] ?? const []));
      } catch (e) {
        if (mounted) _toast('Не удалось загрузить архив $bar: $e');
      }
    }
  }

  void _runBacktest() {
    if (_candles.length < 100) { _toast('Для бэктеста нужно минимум 100 свечей выбранного периода.'); return; }
    try {
      final engine = const BacktestEngine();
      final result = engine.run(_candles, const BacktestConfig());
      final walk = engine.walkForward(_candles, folds: 3);
      setState(() { _backtestResult = result; _walkForwardResult = walk; });
    } catch (e) { _toast('Ошибка бэктеста: $e'); }
  }

  Future<void> _checkPaperGuard(double last) async {
    final now = DateTime.now();
    if (now.difference(_lastGuardCheck).inSeconds < 2) return;
    _lastGuardCheck = now;
    try {
      _guardRunning = await FlutterBackgroundService().isRunning();
    } catch (_) {
      _guardRunning = false;
    }
    if (!_guardRunning) _managePaperPosition(last);
  }

  void _managePaperPosition(double last) {
    if (_paper.openPosition == null) return;
    final closed = _paper.markPrice(last);
    if (closed != null) {
      _positionState = 'PAPER закрыта: ${closed.reason} • NET ${(closed.realizedPnl - closed.fees).toStringAsFixed(2)} USDT';
      _guardStatus = 'позиция закрыта';
      _guardRunning = false;
      stopPaperGuardService();
    }
    if (closed != null || DateTime.now().difference(_lastPaperPersist).inSeconds >= 1) {
      _persistPaper();
    }
  }

  Future<void> _switchMarket(String type) async {
    if (_marketType == type) return;
    if (_paper.openPosition != null) { _toast('Сначала закройте PAPER-позицию на текущем инструменте.'); return; }
    setState(() { _marketType = type; _selected = null; if (type == 'SPOT') _leverage = 1; });
    await _market.disconnect();
    await _loadMarket();
  }

  Future<void> _selectInstrument(MarketInstrument instrument) async {
    if (_paper.openPosition != null) { _toast('Сначала закройте PAPER-позицию на текущем инструменте.'); return; }
    Navigator.pop(context);
    setState(() { _selected = instrument; _price = instrument.lastPrice; _bid = instrument.bidPrice; _ask = instrument.askPrice; _candles.clear(); });
    try {
      await _connectSelected();
    } catch (e) {
      if (mounted) setState(() => _status = 'Ошибка WebSocket: $e');
    }
  }

  Future<void> _restoreAutoSettings() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      _perTradeMargin.text = prefs.getString('botok.auto.margin') ?? '10';
      _autoProfitTarget.text = prefs.getString('botok.auto.target') ?? '5';
      _leverage = prefs.getDouble('botok.auto.leverage') ?? 1;
      final savedMarketType = prefs.getString('botok.auto.marketType');
      if (savedMarketType == 'SPOT' || savedMarketType == 'SWAP') {
        _marketType = savedMarketType!;
      }
      final enabled = prefs.getBool('botok.auto.enabled') ?? false;
      if (mounted) {
        setState(() {
          _autoProfitEnabled = enabled;
          if (enabled) _autoScanStatus = 'Восстановление фонового автосканера…';
        });
      }
      if (enabled) {
        await _paperRestore;
        if (!mounted) return;
        _autoScanTimer?.cancel();
        _autoScanTimer = Timer.periodic(const Duration(seconds: 60), (_) => _maybeAutoOpen());
        try {
          await startPaperGuardService();
          _guardRunning = await FlutterBackgroundService().isRunning();
          _guardStatus = _guardRunning ? 'автосканер восстановлен' : 'фоновый сервис не подтвердил запуск';
        } catch (error) {
          _guardRunning = false;
          _guardStatus = 'ошибка восстановления автосканера: $error';
        }
      }
    } catch (_) {}
  }

  Future<void> _saveAutoSettings() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('botok.auto.margin', _perTradeMargin.text.trim());
    await prefs.setString('botok.auto.target', _autoProfitTarget.text.trim());
    await prefs.setDouble('botok.auto.leverage', _leverage);
    await prefs.setString('botok.auto.marketType', _marketType);
  }

  Future<void> _setAutoProfit(bool enabled) async {
    if (!enabled) {
      _autoScanTimer?.cancel();
      _autoScanTimer = null;
      setState(() {
        _autoProfitEnabled = false;
        _autoScanStatus = 'Пауза';
      });
      try {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setBool('botok.auto.enabled', false);
        refreshPaperGuardService();
      } catch (_) {}
      return;
    }
    final margin = double.tryParse(_perTradeMargin.text.replaceAll(',', '.')) ?? 0;
    final target = double.tryParse(_autoProfitTarget.text.replaceAll(',', '.')) ?? 0;
    if (!margin.isFinite || margin <= 0 || !target.isFinite || target <= 0 || target > 100) {
      _toast('Проверьте сумму залога и чистую цель прибыли.');
      return;
    }
    if (_paper.availableBalance < margin) {
      _toast('Свободного PAPER-баланса меньше заданного залога на сделку.');
      return;
    }
    if (_marketType == 'SPOT') _leverage = 1;
    await _saveAutoSettings();
    setState(() {
      _autoProfitEnabled = true;
      _autoScanStatus = 'Сканирование рынка…';
    });
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool('botok.auto.enabled', true);
      await _persistPaper();
      await startPaperGuardService();
      _guardRunning = await FlutterBackgroundService().isRunning();
      _guardStatus = _guardRunning ? 'фоновый автосканер запущен' : 'фоновый сервис не подтвердил запуск';
    } catch (error) {
      _guardRunning = false;
      _guardStatus = 'ошибка запуска фонового агента: $error';
    }
    _autoScanTimer?.cancel();
    _autoScanTimer = Timer.periodic(const Duration(seconds: 60), (_) => _maybeAutoOpen());
    if (!_guardRunning) await _maybeAutoOpen();
  }

  Future<void> _maybeAutoOpen() async {
    if (!_autoProfitEnabled || _autoScanBusy || _autoEntryInProgress ||
        _paper.openPosition != null || !_paperReady || _instruments.isEmpty) return;
    try {
      if (await FlutterBackgroundService().isRunning()) return;
    } catch (_) {}
    if (DateTime.now().difference(_lastAutoEntryAt) < const Duration(minutes: 3)) return;
    final margin = double.tryParse(_perTradeMargin.text.replaceAll(',', '.')) ?? 0;
    final target = double.tryParse(_autoProfitTarget.text.replaceAll(',', '.')) ?? 0;
    if (!margin.isFinite || margin <= 0 || !target.isFinite || target <= 0 || target > 100) return;
    if (_paper.availableBalance < margin) {
      if (mounted) setState(() => _autoScanStatus = 'Недостаточно свободного баланса для следующей сделки');
      return;
    }
    _autoScanBusy = true;
    _autoEntryInProgress = true;
    try {
      if (mounted) setState(() => _autoScanStatus = 'Сканирование ${_instruments.length} инструментов…');
      final opportunity = await _scanner.scan(
        instruments: _instruments,
        marketType: _marketType,
        loadCandles: (instrumentId, timeframe, limit) =>
            _market.loadCandles(instrumentId, bar: timeframe, limit: limit),
      );
      if (!_autoProfitEnabled || _paper.openPosition != null || opportunity == null) {
        if (mounted) setState(() => _autoScanStatus = 'Подходящего сигнала нет • продолжаю поиск');
        return;
      }
      if (mounted) {
        setState(() {
          _selected = opportunity.instrument;
          _price = opportunity.instrument.lastPrice > 0 ? opportunity.instrument.lastPrice : opportunity.price;
          _bid = opportunity.instrument.bidPrice;
          _ask = opportunity.instrument.askPrice;
          _candlesByTimeframe.clear();
          _candles.clear();
          _autoScanStatus = 'Кандидат: ${opportunity.instrument.id} • ${opportunity.analysis.signal.direction}';
        });
      }
      await _connectSelected();
      if (!_autoProfitEnabled || _paper.openPosition != null || !_analysis.isAligned ||
          _analysis.recommendation == 'ЖДАТЬ' ||
          (_marketType == 'SPOT' && _analysis.signal.direction == 'SHORT')) {
        if (mounted) setState(() => _autoScanStatus = 'Сигнал ослаб при перепроверке • жду следующий');
        return;
      }
      await _openPaper(automatic: true);
      if (_paper.openPosition != null && mounted) {
        setState(() => _autoScanStatus = 'PAPER ${_paper.openPosition!.instrumentId} • ${_paper.openPosition!.plan.direction}');
      } else if (mounted) {
        setState(() => _autoScanStatus = 'Сделка не открыта • повторный поиск');
      }
    } catch (error) {
      if (mounted) setState(() => _autoScanStatus = 'Ошибка сканирования: $error');
    } finally {
      _autoScanBusy = false;
      _autoEntryInProgress = false;
    }
  }

  Future<void> _showAutoSettings() async {
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, dialogSetState) => AlertDialog(
          backgroundColor: _panel,
          title: const Text('НАСТРОЙКИ АВТОАГЕНТА'),
          content: SizedBox(
            width: 360,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Залог на одну сделку (USDT)', style: TextStyle(color: _muted, fontSize: 11)),
                TextField(controller: _perTradeMargin, enabled: !_autoProfitEnabled, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(suffixText: 'USDT')),
                const SizedBox(height: 12),
                const Text('Чистая прибыль после комиссий', style: TextStyle(color: _muted, fontSize: 11)),
                TextField(controller: _autoProfitTarget, enabled: !_autoProfitEnabled, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(suffixText: '%')),
                const SizedBox(height: 12),
                Text('Плечо: ${_marketType == 'SPOT' ? '1' : _leverage.toStringAsFixed(1)}x', style: const TextStyle(color: _muted, fontSize: 11)),
                Slider(
                  value: _marketType == 'SPOT' ? 1 : _leverage.clamp(1, 20).toDouble(),
                  min: 1,
                  max: 20,
                  divisions: 19,
                  onChanged: _autoProfitEnabled || _marketType == 'SPOT'
                      ? null
                      : (value) => dialogSetState(() => _leverage = value),
                ),
                const Text('Для Spot плечо фиксировано 1x. Для SWAP размер позиции округляется по контрактным параметрам OKX.', style: TextStyle(color: _muted, fontSize: 10)),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('ЗАКРЫТЬ')),
            FilledButton(onPressed: _autoProfitEnabled ? null : () async {
              final margin = double.tryParse(_perTradeMargin.text.replaceAll(',', '.')) ?? 0;
              final target = double.tryParse(_autoProfitTarget.text.replaceAll(',', '.')) ?? 0;
              if (margin <= 0 || target <= 0 || target > 100) {
                _toast('Сумма должна быть больше 0, цель — от 0 до 100%.');
                return;
              }
              await _saveAutoSettings();
              if (mounted) Navigator.pop(dialogContext);
            }, child: const Text('СОХРАНИТЬ')),
          ],
        ),
      ),
    );
  }

  Future<void> _openPaper({bool automatic = false}) async {
    if (!_paperReady) { _toast('Демо-кошелёк ещё загружается.'); return; }
    if (_paper.openPosition != null) { _toast('Сначала закройте текущую PAPER-позицию.'); return; }
    if (_price <= 0) { _toast('Нет актуальной цены OKX'); return; }
    final analysis = _analysis;
    final signal = analysis.signal;
    if (automatic ? !analysis.isAligned : analysis.recommendation == 'ЖДАТЬ') {
      _toast('Сейчас рекомендация: ЖДАТЬ. Нужны минимум три согласованных таймфрейма и сила сигнала от 60%.');
      return;
    }
    if (_marketType == 'SPOT' && signal.direction == 'SHORT') {
      _toast('SHORT нельзя открыть на спотовом рынке. Переключите рынок на SWAP.');
      return;
    }
    if (signal.confidence < 56) {
      _toast('Сигнал слабый: ${signal.confidence.toStringAsFixed(1)}%. Ожидание.');
      return;
    }
    late final TradePlan plan;
    try {
      final requestedMargin = automatic
          ? (double.tryParse(_perTradeMargin.text.replaceAll(',', '.')) ?? 0)
          : _paper.availableBalance;
      if (automatic && requestedMargin > _paper.availableBalance) {
        _toast('Недостаточно свободного баланса для заданного залога.');
        return;
      }
      final instrument = _selected;
      if (instrument == null) {
        _toast('Не выбран инструмент OKX.');
        return;
      }
      final executableEntry = signal.direction == 'LONG'
          ? (_ask > 0 ? _ask : instrument.askPrice > 0 ? instrument.askPrice : _price)
          : (_bid > 0 ? _bid : instrument.bidPrice > 0 ? instrument.bidPrice : _price);
      plan = buildTradePlan(
        direction: signal.direction,
        entry: executableEntry,
        capital: requestedMargin,
        riskPercent: _riskPercent,
        leverage: _marketType == 'SPOT' ? 1 : _leverage,
        useFullCollateral: automatic,
        contractSize: _selected!.contractSize,
        lotSize: _selected!.lotSize,
        minSize: _selected!.minSize,
        tickSize: _selected!.tickSize,
        autoProfitTargetPercent: automatic ? (double.tryParse(_autoProfitTarget.text.replaceAll(',', '.')) ?? 0) : 0,
      );
    } catch (e) {
      _toast('Не удалось рассчитать сделку: $e');
      return;
    }
    if (_confirmMode && !automatic) {
      final approved = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          backgroundColor: _panel,
          title: const Text('Подтвердить PAPER-сделку?'),
          content: Text('${plan.direction}\\nВход: ${_fmt(plan.entry)}\\nЗалог: ${(plan.entry * plan.quantity / plan.leverage).toStringAsFixed(2)} USDT\\nStop Loss: ${_fmt(plan.stopLoss)}\\nTP1: ${_fmt(plan.takeProfit1)}\\nTP2: ${_fmt(plan.takeProfit2)}\\nРиск: ${plan.riskAmount.toStringAsFixed(2)} USDT'),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Отмена')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Подтвердить')),
          ],
        ),
      );
      if (approved != true) return;
    }
    try {
      _paper.open(plan, instrumentId: _selected!.id);
      if (automatic) _lastAutoEntryAt = DateTime.now();
      setState(() => _positionState = automatic ? 'АВТО PAPER ${plan.direction} • цель ${plan.autoProfitTargetPercent.toStringAsFixed(1)}% от залога' : 'PAPER ${plan.direction} • SL/TP активны');
      await _persistPaper();
    } catch (e) {
      _toast('PAPER-сделка не открыта: $e');
      return;
    }
    try {
      _guardStatus = 'запуск фонового контроля';
      await startPaperGuardService();
      _guardRunning = await FlutterBackgroundService().isRunning();
      _guardStatus = _guardRunning ? 'фоновый контроль запущен' : 'фоновый контроль не подтвердил запуск';
    } catch (e) {
      _guardRunning = false;
      _guardStatus = 'ошибка запуска фонового контроля';
      _toast('Сделка открыта в Paper Trading, но фоновая защита не запущена: $e');
    }
  }

  Future<void> _closePaper() async {
    final position = _paper.openPosition;
    final executableExit = position == null ? _price : position.isLong ? (_bid > 0 ? _bid : _price) : (_ask > 0 ? _ask : _price);
    final trade = _paper.closeManually(executableExit > 0 ? executableExit : null);
    if (trade == null) return;
    setState(() => _positionState = 'Закрыта вручную • NET ${(trade.realizedPnl - trade.fees).toStringAsFixed(2)} USDT');
    await _persistPaper();
    _guardStatus = 'позиция закрыта вручную';
    _guardRunning = _autoProfitEnabled;
    if (_autoProfitEnabled) {
      refreshPaperGuardService();
    } else {
      stopPaperGuardService();
    }
  }

  void _toast(String message) {
    if (!mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(SnackBar(content: Text(message, maxLines: 2, overflow: TextOverflow.ellipsis), duration: const Duration(seconds: 3), behavior: SnackBarBehavior.floating));
  }

  String _fmt(double value) => value >= 100 ? value.toStringAsFixed(2) : value.toStringAsFixed(5);

  @override
  void dispose() {
    _reconnectTimer?.cancel();
    _feed?.cancel();
    _guardFeed?.cancel();
    _guardStatusFeed?.cancel();
    _guardErrorFeed?.cancel();
    _guardStoppedFeed?.cancel();
    _market.dispose();
    _search.dispose();
    _perTradeMargin.dispose();
    _autoScanTimer?.cancel();
    _autoProfitTarget.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final selected = _selected;
    final analysis = _analysis;
    final signal = analysis.signal;
    final rec = analysis.recommendation;
    final color = rec == 'LONG' ? _green : rec == 'SHORT' ? _red : Colors.orange;
    return Scaffold(
      appBar: AppBar(backgroundColor: _bg, toolbarHeight: 52,
        title: const Row(children: [Icon(Icons.auto_graph_rounded, color: _blue), SizedBox(width: 8), Text('BOTok', style: TextStyle(fontWeight: FontWeight.w800)), SizedBox(width: 8), Text('OKX', style: TextStyle(fontSize: 11, color: _muted))]),
        actions: [IconButton(onPressed: _loading ? null : _loadMarket, icon: const Icon(Icons.refresh))]),
      body: SafeArea(child: RefreshIndicator(onRefresh: _loadMarket, child: ListView(
        padding: const EdgeInsets.fromLTRB(12, 4, 12, 14),
        children: [
          _statusBar(), const SizedBox(height: 6), _topBalanceCard(), const SizedBox(height: 7), _marketSelector(), const SizedBox(height: 7),
          _compactInstrumentCard(selected), const SizedBox(height: 7),
          Container(padding: const EdgeInsets.all(13), decoration: BoxDecoration(color: _panel, borderRadius: BorderRadius.circular(16), border: Border.all(color: color.withValues(alpha: .45))),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('РЕКОМЕНДАЦИЯ АГЕНТА', style: TextStyle(color: _muted, fontSize: 10, fontWeight: FontWeight.bold)),
              Row(children: [Expanded(child: Text(rec, style: TextStyle(color: color, fontSize: 32, fontWeight: FontWeight.w900))), Text('Сила ${signal.confidence.toStringAsFixed(0)}/100', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold))]),
              Text(rec == 'ЖДАТЬ' ? 'Направление не подтверждено — ждём.' : rec == 'LONG' ? 'Преимущество сценария роста.' : 'Преимущество сценария снижения.', style: const TextStyle(color: _muted, fontSize: 11)),
              const SizedBox(height: 9),
              Row(children: [Expanded(child: _probability('РОСТ', signal.longProbability, _green)), const SizedBox(width: 10), Expanded(child: _probability('СНИЖЕНИЕ', signal.shortProbability, _red))]),
              const SizedBox(height: 6),
              Text('Согласие интервалов ${analysis.agreementPercent.toStringAsFixed(0)}% • активны ${analysis.activeTimeframes}/7', style: const TextStyle(color: _muted, fontSize: 10)),
              if (_marketType == 'SPOT' && rec == 'SHORT') const Text('Для SHORT переключите рынок на FUTURES / SWAP.', style: TextStyle(color: Colors.orange, fontSize: 10)),
            ])),
          const SizedBox(height: 7), _compactForecastCard(), const SizedBox(height: 7), _compactChartCard(), const SizedBox(height: 7),
          _autoProfitCard(), const SizedBox(height: 7), _quickControlsCard(rec), const SizedBox(height: 7), _compactPositionCard(),
          const SizedBox(height: 6),
          const Text('Котировки OKX LIVE • Только PAPER Trading, реальные ордера не отправляются.', textAlign: TextAlign.center, style: TextStyle(color: _muted, fontSize: 9)),
        ],
      ))),
    );
  }

  Widget _compactInstrumentCard(MarketInstrument? instrument) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 9),
    decoration: BoxDecoration(color: _panel, borderRadius: BorderRadius.circular(13)),
    child: Row(children: [
      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(instrument?.id ?? 'Загрузка…', style: const TextStyle(color: _muted, fontSize: 10)),
        Text(_price > 0 ? _fmt(_price) : '—', style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800)),
      ])),
      Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
        Text('BID ${_bid > 0 ? _fmt(_bid) : '—'}', style: const TextStyle(color: _green, fontSize: 10)),
        Text('ASK ${_ask > 0 ? _fmt(_ask) : '—'}', style: const TextStyle(color: _red, fontSize: 10)),
      ]),
    ]),
  );

  Widget _compactForecastCard() {
    final candles = (_candlesByTimeframe['15m'] ?? _candles).where((c) => c.isClosed).toList();
    final f = buildMarketForecast(candles);
    return Container(padding: const EdgeInsets.all(11), decoration: BoxDecoration(color: _panel, borderRadius: BorderRadius.circular(13)),
      child: f == null ? const Text('Прогноз формируется: недостаточно закрытых свечей.', style: TextStyle(color: _muted, fontSize: 10))
      : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('ПРОГНОЗ ДВИЖЕНИЯ • 15 МИН', style: TextStyle(color: _muted, fontSize: 10, fontWeight: FontWeight.bold)),
        Row(children: [
          Expanded(child: Text(f.projectedMedian >= f.currentPrice ? 'Ожидается рост' : 'Ожидается снижение', style: TextStyle(color: f.projectedMedian >= f.currentPrice ? _green : _red, fontSize: 16, fontWeight: FontWeight.bold))),
          Text('${f.volatilityPercent.toStringAsFixed(2)}% волат.', style: const TextStyle(color: _muted, fontSize: 10)),
        ]),
        Text('Ориентир ${_fmt(f.projectedMedian)} • диапазон ${_fmt(f.projectedLower)} — ${_fmt(f.projectedUpper)}', style: const TextStyle(fontSize: 10)),
        const Text('Модельный сценарий, не гарантия результата.', style: TextStyle(color: _muted, fontSize: 9)),
      ]));
  }

  Widget _compactChartCard() => Container(padding: const EdgeInsets.fromLTRB(10, 2, 10, 8), decoration: BoxDecoration(color: _panel, borderRadius: BorderRadius.circular(13)),
    child: Column(children: [
      Row(children: [
        const Expanded(child: Text('ГРАФИК', style: TextStyle(color: _muted, fontSize: 10, fontWeight: FontWeight.bold))),
        DropdownButton<String>(value: _selectedTimeframe, dropdownColor: _panel, underline: const SizedBox.shrink(), isDense: true,
          items: MarketTimeframe.all.map((tf) => DropdownMenuItem(value: tf.bar, child: Text(tf.label, style: const TextStyle(fontSize: 10)))).toList(),
          onChanged: (v) { if (v != null) _setTimeframe(v); }),
      ]),
      SizedBox(height: 390, child: _candles.length < 2 ? const Center(child: Text('Загрузка свечей…', style: TextStyle(color: _muted, fontSize: 10)))
        : CustomPaint(painter: _CandlePainter(List<MarketCandle>.from(_candles), forecast: buildMarketForecast(_candles.where((c) => c.isClosed).toList()), position: _paper.openPosition), child: const SizedBox.expand())),
    ]));

  Widget _topBalanceCard() => Container(
    padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 10),
    decoration: BoxDecoration(color: _panel, borderRadius: BorderRadius.circular(13)),
    child: Row(children: [
      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('БАЛАНС PAPER', style: TextStyle(color: _muted, fontSize: 9, fontWeight: FontWeight.bold)),
        Text(_paperReady ? '${_paper.equity.toStringAsFixed(2)} USDT' : '—', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
        if (_paper.openPosition != null)
          Text('Текущая сделка NET ${_paper.positionNetPnl >= 0 ? '+' : ''}${_paper.positionNetPnl.toStringAsFixed(2)} USDT', style: TextStyle(color: _paper.positionNetPnl >= 0 ? _green : _red, fontSize: 10, fontWeight: FontWeight.bold)),
        Text('Комиссии всего ${_paper.totalFees.toStringAsFixed(2)} USDT • выход сейчас ≈ ${_paper.estimatedExitFee.toStringAsFixed(2)}', style: const TextStyle(color: _muted, fontSize: 9)),
        Text('Доступно ${_paperReady ? _paper.availableBalance.toStringAsFixed(2) : '—'} USDT', style: const TextStyle(color: _muted, fontSize: 9)),
      ])),
      Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
        Text('PnL ${_paper.netAccountPnl >= 0 ? '+' : ''}${_paper.netAccountPnl.toStringAsFixed(2)} USDT', style: TextStyle(color: _paper.netAccountPnl >= 0 ? _green : _red, fontSize: 11, fontWeight: FontWeight.bold)),
        Text('Залог ${_paper.marginUsed.toStringAsFixed(2)} USDT', style: const TextStyle(color: _muted, fontSize: 9)),
      ]),
    ]),
  );

  Widget _autoProfitCard() => Container(
    padding: const EdgeInsets.all(11),
    decoration: BoxDecoration(color: _panel, borderRadius: BorderRadius.circular(13), border: Border.all(color: _autoProfitEnabled ? _blue.withValues(alpha: .6) : Colors.transparent)),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        const Expanded(child: Text('АВТОАГЕНТ • ОДНА СДЕЛКА ЗА РАЗ', style: TextStyle(fontSize: 10, color: _muted, fontWeight: FontWeight.bold))),
        IconButton(onPressed: _autoProfitEnabled ? null : _showAutoSettings, icon: const Icon(Icons.settings, size: 18)),
        FilledButton.icon(
          onPressed: () => _setAutoProfit(!_autoProfitEnabled),
          icon: Icon(_autoProfitEnabled ? Icons.pause_rounded : Icons.play_arrow_rounded, size: 16),
          label: Text(_autoProfitEnabled ? 'ПАУЗА' : 'ЗАПУСТИТЬ'),
          style: FilledButton.styleFrom(backgroundColor: _autoProfitEnabled ? Colors.orange.withValues(alpha: .18) : _blue.withValues(alpha: .2), foregroundColor: _autoProfitEnabled ? Colors.orange : _blue, padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8), textStyle: const TextStyle(fontSize: 10, fontWeight: FontWeight.bold)),
        ),
      ]),
      Text('${_perTradeMargin.text} USDT на сделку • чистая цель ${_autoProfitTarget.text}% • плечо ${_marketType == 'SPOT' ? '1' : _leverage.toStringAsFixed(1)}x', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
      const SizedBox(height: 5),
      Text(_autoProfitEnabled ? _autoScanStatus : 'Запуск: поиск лучшей пары OKX → LONG/SHORT → PAPER → закрытие по чистой цели. Только виртуальные сделки.', style: const TextStyle(color: _muted, fontSize: 9)),
      const Text('Поиск новых входов выполняется, пока приложение активно. Открытая PAPER-позиция отдельно контролируется сервисом.', style: TextStyle(color: _muted, fontSize: 9)),
    ]),
  );

  Widget _quickControlsCard(String rec) {
    final plan = _paperReady && _price > 0 && _paper.availableBalance > 0 && rec != 'ЖДАТЬ' ? _tryPlan(rec) : null;
    return Container(padding: const EdgeInsets.all(11), decoration: BoxDecoration(color: _panel, borderRadius: BorderRadius.circular(13)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [const Expanded(child: Text('ПАРАМЕТРЫ СДЕЛКИ', style: TextStyle(color: _muted, fontSize: 10, fontWeight: FontWeight.bold))), Text('Риск ${_riskPercent.toStringAsFixed(1)}%', style: const TextStyle(fontSize: 10))]),
        Slider(value: _riskPercent, min: .25, max: 3, divisions: 11, onChanged: (v) => setState(() => _riskPercent = v)),
        Row(children: [
          const Text('Плечо', style: TextStyle(color: _muted, fontSize: 10)),
          Expanded(child: Slider(value: _leverage.clamp(1, 20).toDouble(), min: 1, max: 20, divisions: 19, onChanged: _marketType == 'SWAP' ? (v) => setState(() => _leverage = v) : null)),
          Text(_marketType == 'SWAP' ? '${_leverage.toStringAsFixed(0)}x' : 'SPOT', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
        ]),
        if (plan != null) Wrap(spacing: 10, runSpacing: 4, children: [
          Text('Вход ${_fmt(plan.entry)}', style: const TextStyle(fontSize: 10)),
          Text('SL ${_fmt(plan.stopLoss)}', style: const TextStyle(color: _red, fontSize: 10)),
          Text('TP ${_fmt(plan.takeProfit1)} / ${_fmt(plan.takeProfit2)}', style: const TextStyle(color: _green, fontSize: 10)),
          Text('Риск ${plan.riskAmount.toStringAsFixed(2)} USDT', style: const TextStyle(fontSize: 10)),
        ]),
        Row(children: [
          Expanded(child: Text(_confirmMode ? 'Подтверждать открытие' : 'Без подтверждения', style: const TextStyle(color: _muted, fontSize: 10))),
          Switch(value: _confirmMode, onChanged: (v) => setState(() => _confirmMode = v)),
        ]),
        SizedBox(width: double.infinity, child: FilledButton(
          onPressed: _paperReady && _paper.openPosition == null && rec != 'ЖДАТЬ' && !(_marketType == 'SPOT' && rec == 'SHORT') ? _openPaper : null,
          child: Text(_paper.openPosition != null ? 'ПОЗИЦИЯ ОТКРЫТА' : rec == 'ЖДАТЬ' ? 'ЖДЁМ СИГНАЛ' : 'ОТКРЫТЬ PAPER ПО СИГНАЛУ • ${rec}'),
        )),
      ]));
  }

  Widget _compactPositionCard() {
    final p = _paper.openPosition;
    if (p == null) return Container(padding: const EdgeInsets.all(11), decoration: BoxDecoration(color: _panel, borderRadius: BorderRadius.circular(13)),
      child: Text(_paperReady ? 'PAPER: нет позиции • Баланс ${_paper.availableBalance.toStringAsFixed(2)} USDT' : 'Загрузка PAPER-кошелька…', style: const TextStyle(color: _muted, fontSize: 10)));
    return Container(padding: const EdgeInsets.all(11), decoration: BoxDecoration(color: _panel, borderRadius: BorderRadius.circular(13)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('PAPER ${p.plan.direction} • ${p.instrumentId}', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 11)),
        Text('ЧИСТЫЙ PnL: ${_paper.positionNetPnl >= 0 ? '+' : ''}${_paper.positionNetPnl.toStringAsFixed(2)} USDT', style: TextStyle(color: _paper.positionNetPnl >= 0 ? _green : _red, fontSize: 13, fontWeight: FontWeight.bold)),
        Text('Комиссия входа ${p.entryFee.toStringAsFixed(3)} • TP1 комиссии ${p.partialFees.toStringAsFixed(3)} • выход сейчас ≈ ${_paper.estimatedExitFee.toStringAsFixed(3)} USDT', style: const TextStyle(color: _muted, fontSize: 9)),
        Text('SL ${_fmt(p.effectiveStopLoss)} • TP1 ${_fmt(p.plan.takeProfit1)} • TP2 ${_fmt(p.plan.takeProfit2)}', style: const TextStyle(color: _muted, fontSize: 10)),
        if (p.plan.autoProfitTargetPercent > 0)
          Text('Автозакрытие: +${p.plan.autoProfitTargetPercent.toStringAsFixed(1)}% от начального залога', style: const TextStyle(color: _green, fontSize: 10)),
        Align(alignment: Alignment.centerRight, child: TextButton(onPressed: _closePaper, child: const Text('ЗАКРЫТЬ'))),
      ]));
  }

  // ignore: unused_element
  Widget _btcCorrelationCard() {
    final correlation = calculateReturnCorrelation(
      _candlesByTimeframe['1m'] ?? const <MarketCandle>[],
      _btcCandles,
    );
    final value = correlation == null ? 'Недостаточно данных' : correlation.toStringAsFixed(3);
    final interpretation = correlation == null
        ? 'Нужно минимум 30 совпадающих доходностей.'
        : correlation >= 0.7
            ? 'Сильная положительная связь с BTC.'
            : correlation <= -0.7
                ? 'Сильная обратная связь с BTC.'
                : 'Связь с BTC умеренная или слабая.';
    return _card(title: 'КОРРЕЛЯЦИЯ С BTC • 1m', child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(value, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: _blue)),
      Text(interpretation, style: const TextStyle(color: _muted, fontSize: 10)),
      const Text('Pearson correlation по совпадающим минутным доходностям; это контекст риска, не направление сделки.', style: TextStyle(color: _muted, fontSize: 9)),
    ]));
  }

  // ignore: unused_element
  Widget _derivativesFeedCard() => _card(
    title: 'ДЕРИВАТИВНЫЕ ДАННЫЕ OKX • LIVE',
    child: Column(children: [
      Row(children: [
        Expanded(child: _miniMetric('FUNDING RATE', '${(_fundingRate * 100).toStringAsFixed(4)}%', _fundingRate >= 0 ? _red : _green)),
        Expanded(child: _miniMetric('OPEN INTEREST', _openInterestUsd > 0 ? '${(_openInterestUsd / 1000000).toStringAsFixed(2)}M USD' : '—', _blue)),
        Expanded(child: _miniMetric('OI Δ', '${_openInterestChangePercent >= 0 ? '+' : ''}${_openInterestChangePercent.toStringAsFixed(2)}%', _openInterestChangePercent >= 0 ? _green : _red)),
      ]),
      const SizedBox(height: 8),
      Row(children: [
        Expanded(child: _miniMetric('LIQ. EVENTS', '$_recentLiquidationEvents', Colors.orange)),
        Expanded(child: _miniMetric('LONG LIQ.', _longLiquidationContracts.toStringAsFixed(2), _red)),
        Expanded(child: _miniMetric('SHORT LIQ.', _shortLiquidationContracts.toStringAsFixed(2), _green)),
      ]),
      const Text('Ликвидации — только недавние события канала OKX, не полный объём ликвидаций рынка. OI Δ — изменение между последними полученными обновлениями.', style: TextStyle(color: _muted, fontSize: 9)),
    ]),
  );

  Widget _statusBar() => Container(
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
    decoration: BoxDecoration(color: _panel, borderRadius: BorderRadius.circular(12)),
    child: Row(children: [
      Container(width: 8, height: 8, decoration: BoxDecoration(color: _status.startsWith('LIVE') ? _green : Colors.orange, shape: BoxShape.circle)),
      const SizedBox(width: 9),
      Expanded(child: Text(_status, style: const TextStyle(color: _muted, fontSize: 12), maxLines: 1, overflow: TextOverflow.ellipsis)),
      if (_loading) const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)),
    ]),
  );

  Widget _marketSelector() => Row(children: [
    Expanded(child: _choice('SPOT', 'SPOT', _marketType == 'SPOT')),
    const SizedBox(width: 8),
    Expanded(child: _choice('SWAP', 'FUTURES / SWAP', _marketType == 'SWAP')),
    const SizedBox(width: 8),
    IconButton.filledTonal(onPressed: _showInstrumentPicker, icon: const Icon(Icons.search)),
  ]);

  Widget _choice(String value, String label, bool active) => FilledButton(
    style: FilledButton.styleFrom(
      backgroundColor: active ? _blue.withValues(alpha: 0.22) : _panel,
      foregroundColor: active ? _blue : _muted,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
    onPressed: () => _switchMarket(value),
    child: Text(label, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
  );

  // ignore: unused_element
  Widget _instrumentCard(MarketInstrument? instrument) => _card(
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        Expanded(child: Text(instrument?.id ?? '—', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700))),
        const Text('LIVE PRICE', style: TextStyle(fontSize: 10, color: _muted)),
      ]),
      const SizedBox(height: 7),
      Text(_price > 0 ? _fmt(_price) : '—', style: const TextStyle(fontSize: 30, fontWeight: FontWeight.w800)),
      const SizedBox(height: 8),
      Row(children: [
        _miniMetric('BID', _bid > 0 ? _fmt(_bid) : '—', _green),
        const SizedBox(width: 18),
        _miniMetric('ASK', _ask > 0 ? _fmt(_ask) : '—', _red),
        const Spacer(),
        Text(instrument == null ? '' : '${instrument.type}', style: const TextStyle(color: _muted, fontSize: 10)),
      ]),
    ]),
  );

  // ignore: unused_element
  Widget _chartCard() => _card(
    title: 'OKX • СВЕЧИ $_selectedTimeframe • LONG / SHORT ЗОНЫ',
    child: Column(children: [
      Align(alignment: Alignment.centerRight, child: DropdownButton<String>(
        value: _selectedTimeframe,
        dropdownColor: _panel,
        items: MarketTimeframe.all.map((tf) => DropdownMenuItem(value: tf.bar, child: Text(tf.label))).toList(),
        onChanged: (value) { if (value != null) _setTimeframe(value); },
      )),
      SizedBox(height: 230, child: _candles.length < 2
        ? const Center(child: Text('Загрузка OHLC-свечей OKX…', style: TextStyle(color: _muted, fontSize: 12)))
        : CustomPaint(
            painter: _CandlePainter(List<MarketCandle>.from(_candles), forecast: buildMarketForecast(_candles.where((c) => c.isClosed).toList()), position: _paper.openPosition),
            child: const SizedBox.expand(),
          )),
    ]),
  );

  // ignore: unused_element
  Widget _forecastCard() {
    final closedCandles = _candles.where((candle) => candle.isClosed).toList();
    final forecast = buildMarketForecast(closedCandles);
    final validation = validateMarketForecast(closedCandles, maxSamples: 120);
    final timeframeLabel = MarketTimeframe.all
        .firstWhere((timeframe) => timeframe.bar == _selectedTimeframe, orElse: () => MarketTimeframe.all.first)
        .label;
    return _card(title: 'БУДУЩИЙ РЫНОК • $timeframeLabel • +12 БАРОВ', child: forecast == null
      ? const Text('Для прогноза нужно минимум 25 закрытий выбранного таймфрейма.', style: TextStyle(color: _muted, fontSize: 11))
      : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(height: 170, child: CustomPaint(painter: _ForecastPainter(forecast), child: const SizedBox.expand())),
          Row(children: [
            Expanded(child: _miniMetric('LONG / рост', '${forecast.bullishProbability.toStringAsFixed(1)}%', _green)),
            Expanded(child: _miniMetric('SHORT / снижение', '${forecast.bearishProbability.toStringAsFixed(1)}%', _red)),
          ]),
          _planLine('Горизонт прогноза', '$timeframeLabel × 12 свечей'),
          _planLine('Медианный ориентир', _fmt(forecast.projectedMedian), _blue),
          _planLine('Прогнозный диапазон (95% модельный)', '${_fmt(forecast.projectedLower)} — ${_fmt(forecast.projectedUpper)}'),
          _planLine('Волатильность на горизонт', '${forecast.volatilityPercent.toStringAsFixed(2)}%'),
          if (validation != null) ...[
            const Divider(),
            _planLine('Проверка на прошлых окнах', '${validation.samples} out-of-sample прогнозов'),
            _planLine('Точность направления', '${validation.directionalAccuracyPercent.toStringAsFixed(1)}%'),
            _planLine('Покрытие 95% диапазона', '${validation.intervalCoveragePercent.toStringAsFixed(1)}%'),
            _planLine('Средняя ошибка медианы', '${validation.meanAbsoluteErrorPercent.toStringAsFixed(2)}%'),
          ],
          const Text('Вероятности основаны на нормальном приближении доходностей; ниже показывается скользящая проверка на более поздних свечах. Это не гарантия будущего результата.', style: TextStyle(color: _muted, fontSize: 9)),
        ]));
  }

  // ignore: unused_element
  Widget _timeframeConfluenceCard() {
    final analysis = _analysis;
    final signal = analysis.signal;
    final aligned = analysis.isAligned;
    final color = signal.direction == 'LONG' ? _green : _red;
    return _card(title: 'СВОДКА 7 ТАЙМФРЕЙМОВ • ЕДИНЫЙ АНАЛИЗ', child: Column(children: [
      Row(children: [
        Expanded(child: _miniMetric('ОБЩЕЕ НАПРАВЛЕНИЕ', signal.direction, color)),
        Expanded(child: _miniMetric('СОГЛАСИЕ', '${analysis.agreementPercent.toStringAsFixed(0)}%', aligned ? _green : Colors.orange)),
        Expanded(child: _miniMetric('АКТИВНЫЕ TF', '${analysis.activeTimeframes}/7', _blue)),
      ]),
      const SizedBox(height: 8),
      for (final tf in MarketTimeframe.all) _timeframeRow(tf),
      Text(aligned ? 'Сигналы согласованы по нескольким горизонтам.' : 'Недостаточно согласованных таймфреймов: автоматическое открытие сделки заблокировано.', style: const TextStyle(color: _muted, fontSize: 9)),
      const Text('Внутри: EMA, RSI, MACD, Bollinger, ATR, VWAP, OBV, Stoch RSI, стакан, сделки, funding и динамика OI. Проценты — модельный скоринг, не статистически подтверждённая вероятность.', style: TextStyle(color: _muted, fontSize: 9)),
    ]));
  }

  Widget _timeframeRow(MarketTimeframe tf) {
    final candles = _candlesByTimeframe[tf.bar] ?? const <MarketCandle>[];
    final ready = candles.length >= 25;
    final signal = _analysis.byTimeframe[tf.bar];
    final direction = signal?.direction ?? '—';
    final color = direction == 'LONG' ? _green : _red;
    return Padding(padding: const EdgeInsets.symmetric(vertical: 5), child: Row(children: [
      SizedBox(width: 58, child: Text(tf.label, style: const TextStyle(fontSize: 11))),
      Expanded(child: Text(ready ? direction : 'нет данных', style: TextStyle(fontSize: 11, color: ready ? color : _muted, fontWeight: FontWeight.bold))),
      Text(ready && signal != null ? '${signal.confidence.toStringAsFixed(0)}%' : '—', style: TextStyle(fontSize: 11, color: ready ? color : _muted)),
      SizedBox(width: 76, child: Text('${candles.length} свечей', textAlign: TextAlign.end, style: const TextStyle(fontSize: 9, color: _muted))),
    ]));
  }

  // ignore: unused_element
  Widget _backtestCard() => _card(title: 'ИСТОРИЧЕСКИЙ БЭКТЕСТ • $_selectedTimeframe', child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    Text('${_candles.length} свечей • комиссия 0,1% • проскальзывание 3 bps • старт 1 000 USDT', style: const TextStyle(color: _muted, fontSize: 10)),
    const SizedBox(height: 8),
    SizedBox(width: double.infinity, child: OutlinedButton.icon(onPressed: _runBacktest, icon: const Icon(Icons.science), label: const Text('ЗАПУСТИТЬ БЭКТЕСТ + WALK-FORWARD'))),
    if (_backtestResult != null) ...[
      const Divider(),
      _planLine('Сделок', '${_backtestResult!.tradeCount}'),
      _planLine('Итоговый баланс', '${_backtestResult!.finalBalance.toStringAsFixed(2)} USDT'),
      _planLine('Чистый PnL', '${_backtestResult!.netPnl >= 0 ? '+' : ''}${_backtestResult!.netPnl.toStringAsFixed(2)} USDT', _backtestResult!.netPnl >= 0 ? _green : _red),
      _planLine('Доходность / win rate', '${_backtestResult!.returnPercent.toStringAsFixed(2)}% / ${_backtestResult!.winRate.toStringAsFixed(1)}%'),
      _planLine('Profit factor / max DD', '${_backtestResult!.profitFactor.toStringAsFixed(2)} / ${_backtestResult!.maxDrawdownPercent.toStringAsFixed(2)}%'),
      _planLine('Комиссии', '${_backtestResult!.fees.toStringAsFixed(2)} USDT'),
      _planLine('Walk-forward folds', '${_walkForwardResult?.folds.length ?? 0}'),
      _planLine('PnL тестовых окон', '${_walkForwardResult?.totalNetPnl.toStringAsFixed(2) ?? '—'} USDT'),
      const Text('Бэктест использует только загруженные свечи и упрощённую spot-модель. Результат не гарантирует будущую доходность.', style: TextStyle(color: _muted, fontSize: 9)),
    ],
  ]));

  // ignore: unused_element
  Widget _signalCard(TradeSignal signal) => _card(
    title: 'СОВМЕЩЁННЫЙ СИГНАЛ • LONG / SHORT',
    child: Column(children: [
      Row(children: [
        Expanded(child: _probability('LONG', signal.longProbability, _green)),
        const SizedBox(width: 12),
        Expanded(child: _probability('SHORT', signal.shortProbability, _red)),
      ]),
      const SizedBox(height: 14),
      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        _miniMetric('RSI 14', signal.rsi.toStringAsFixed(1), Colors.white),
        _miniMetric('EMA 9', signal.emaFast == 0 ? '—' : _fmt(signal.emaFast), _blue),
        _miniMetric('EMA 21', signal.emaSlow == 0 ? '—' : _fmt(signal.emaSlow), _blue),
      ]),
      const SizedBox(height: 8),
      Wrap(spacing: 10, runSpacing: 8, children: [
        _miniMetric('MACD hist', signal.macdHistogram.toStringAsFixed(3), signal.macdHistogram >= 0 ? _green : _red),
        _miniMetric('Bollinger %', (signal.bollingerPosition * 100).toStringAsFixed(0), _blue),
        _miniMetric('ATR %', signal.atrPercent.toStringAsFixed(2), Colors.orange),
        _miniMetric('VWAP Δ%', signal.vwapDistancePercent.toStringAsFixed(2), signal.vwapDistancePercent >= 0 ? _green : _red),
        _miniMetric('OBV trend', signal.obvTrend.toStringAsFixed(2), signal.obvTrend >= 0 ? _green : _red),
        _miniMetric('Stoch RSI', signal.stochasticRsi.toStringAsFixed(0), _blue),
      ]),
      const SizedBox(height: 8),
      const Text('Проценты — эвристический скоринг нескольких индикаторов и потоков данных, а не обученная и откалиброванная вероятность.', style: TextStyle(color: _muted, fontSize: 10)),
    ]),
  );

  Widget _probability(String label, double value, Color color) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
      Text(label, style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 12)),
      Text('${value.toStringAsFixed(1)}%', style: TextStyle(color: color, fontSize: 20, fontWeight: FontWeight.w800)),
    ]),
    const SizedBox(height: 6),
    ClipRRect(borderRadius: BorderRadius.circular(6), child: LinearProgressIndicator(value: value / 100, minHeight: 8, color: color, backgroundColor: Colors.white10)),
  ]);

  // ignore: unused_element
  Widget _tradePlanCard(TradeSignal signal) {
    final plan = _paperReady && _price > 0 && _paper.availableBalance > 0 && _analysis.isAligned
      ? _tryPlan(signal.direction)
      : null;
    return _card(
      title: 'ПЛАН СДЕЛКИ • АВТОРАСЧЁТ',
      child: Column(children: [
        _planLine('Доступный капитал', '${_paper.availableBalance.toStringAsFixed(2)} USDT', _green),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: Text('Риск на сделку: ${_riskPercent.toStringAsFixed(1)}%', style: const TextStyle(fontSize: 12))),
          Expanded(child: Text('Плечо: ${_leverage.toStringAsFixed(0)}x', textAlign: TextAlign.end, style: const TextStyle(fontSize: 12))),
        ]),
        Row(children: [
          Expanded(child: Slider(value: _riskPercent, min: 0.25, max: 3, divisions: 11, onChanged: (v) => setState(() => _riskPercent = v))),
          _marketType == 'SWAP'
            ? Expanded(child: Slider(value: _leverage, min: 1, max: 20, divisions: 19, onChanged: (v) => setState(() => _leverage = v)))
            : const Expanded(child: Text('SPOT: без плеча', textAlign: TextAlign.center, style: TextStyle(color: _muted, fontSize: 11))),
        ]),
        if (plan != null) ...[
          _planLine('Направление', plan.direction, plan.direction == 'LONG' ? _green : _red),
          _planLine('Вход', _fmt(plan.entry)),
          _planLine('Stop Loss', _fmt(plan.stopLoss), _red),
          _planLine('Take Profit 1', _fmt(plan.takeProfit1), _green),
          _planLine('Take Profit 2', _fmt(plan.takeProfit2), _green),
          _planLine('Размер позиции', '${plan.quantity.toStringAsFixed(6)} ${selectedBase()}'),
          _planLine('Макс. риск', '${plan.riskAmount.toStringAsFixed(2)} USDT'),
        ] else
          const Text('План появится после получения live-цены и ввода капитала.', style: TextStyle(color: _muted, fontSize: 11)),
        const SizedBox(height: 8),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Режим подтверждения', style: TextStyle(fontSize: 12)),
          subtitle: const Text('Перед каждой paper-сделкой спросить подтверждение', style: TextStyle(fontSize: 10, color: _muted)),
          value: _confirmMode,
          onChanged: (v) => setState(() => _confirmMode = v),
        ),
        SizedBox(width: double.infinity, child: FilledButton.icon(
          onPressed: _paperReady && _paper.openPosition == null ? _openPaper : null,
          icon: const Icon(Icons.play_arrow),
          label: const Text('ПОДТВЕРДИТЬ И ОТКРЫТЬ PAPER-СДЕЛКУ'),
        )),
      ]),
    );
  }

  TradePlan? _tryPlan(String direction) {
    try {
      return buildTradePlan(
        direction: direction,
        entry: _price,
        capital: _paper.availableBalance,
        riskPercent: _riskPercent,
        leverage: _leverage,
      );
    } catch (_) { return null; }
  }

  String selectedBase() => _selected?.base ?? 'coin';

  // ignore: unused_element
  Widget _walletCard() => _card(
    title: 'ДЕМО-КОШЕЛЁК • PAPER USDT',
    child: !_paperReady
      ? const Center(child: CircularProgressIndicator())
      : Column(children: [
          Row(children: [
            Expanded(child: _miniMetric('EQUITY', '${_paper.equity.toStringAsFixed(2)} USDT', _blue)),
            Expanded(child: _miniMetric('ДОСТУПНО', '${_paper.availableBalance.toStringAsFixed(2)} USDT', _green)),
          ]),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(child: _miniMetric('ЗАЛОГ', '${_paper.marginUsed.toStringAsFixed(2)} USDT', Colors.orange)),
            Expanded(child: _miniMetric('CASH', '${_paper.cashBalance.toStringAsFixed(2)} USDT', Colors.white)),
          ]),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(child: _miniMetric('РЕАЛИЗОВАНО', '${_paper.realizedPnl >= 0 ? '+' : ''}${_paper.realizedPnl.toStringAsFixed(2)}', _paper.realizedPnl >= 0 ? _green : _red)),
            Expanded(child: _miniMetric('NET PnL СЧЁТА', '${_paper.netAccountPnl >= 0 ? '+' : ''}${_paper.netAccountPnl.toStringAsFixed(2)}', _paper.netAccountPnl >= 0 ? _green : _red)),
            Expanded(child: _miniMetric('КОМИССИИ', '${_paper.totalFees.toStringAsFixed(2)}', _muted)),
          ]),
          const SizedBox(height: 8),
          Text('Стартовый баланс: ${_paper.initialBalance.toStringAsFixed(2)} USDT • сохраняется на устройстве', style: const TextStyle(color: _muted, fontSize: 10)),
        ]),
  );

  // ignore: unused_element
  Widget _paperCard() {
    final p = _paper.openPosition;
    final pnl = _paper.positionNetPnl;
    final pnlPercent = p == null || p.plan.entry * p.plan.quantity == 0
      ? 0.0
      : pnl / (p.plan.entry * p.plan.quantity) * 100;
    return _card(
      title: 'ОТКРЫТАЯ PAPER-ПОЗИЦИЯ',
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(_positionState, style: const TextStyle(fontSize: 12, color: _muted)),
        if (p != null) ...[
          const SizedBox(height: 10),
          _planLine('Инструмент / направление', '${p.instrumentId} • ${p.plan.direction}', p.isLong ? _green : _red),
          _planLine('Вход / текущая', '${_fmt(p.plan.entry)} / ${_fmt(p.currentPrice)}'),
          _planLine('Объём остатка', p.quantity.toStringAsFixed(6)),
          _planLine('Залог', '${p.margin.toStringAsFixed(2)} USDT'),
          _planLine('Активный Stop Loss', _fmt(p.effectiveStopLoss), _red),
          _planLine('Trailing Stop', p.trailingStopPrice == null ? 'ожидание движения' : _fmt(p.trailingStopPrice!), _blue),
          _planLine('Take Profit 1 / 2', '${_fmt(p.plan.takeProfit1)} / ${_fmt(p.plan.takeProfit2)}', _green),
          _planLine('Текущий PnL', '${pnl >= 0 ? '+' : ''}${pnl.toStringAsFixed(2)} USDT  (${pnlPercent.toStringAsFixed(2)}%)', pnl >= 0 ? _green : _red),
          _planLine('TP1', p.takeProfit1Hit ? '50% зафиксировано' : 'ожидание'),
          _planLine('Фоновый контроль SL/TP', _guardStatus, _guardStatus.contains('ошибка') ? _red : _green),
          SizedBox(width: double.infinity, child: OutlinedButton(
            onPressed: () async {
              final trade = _paper.closeManually();
              if (trade != null) {
                setState(() => _positionState = 'Закрыта вручную • NET ${(trade.realizedPnl - trade.fees).toStringAsFixed(2)} USDT');
                await _persistPaper();
                _guardStatus = 'позиция закрыта вручную';
                _guardRunning = false;
                stopPaperGuardService();
              }
            },
            child: const Text('ЗАКРЫТЬ PAPER-ПОЗИЦИЮ'),
          )),
        ] else
          const Text('Открытых сделок нет. После подтверждения бот откроет демо-позицию и начнёт учитывать PnL.', style: TextStyle(color: _muted, fontSize: 11)),
        if (_paper.closedTrades.isNotEmpty) ...[
          const Divider(height: 22),
          const Text('ПОСЛЕДНИЕ ЗАКРЫТЫЕ СДЕЛКИ', style: TextStyle(color: _muted, fontSize: 10, fontWeight: FontWeight.bold)),
          for (final trade in _paper.closedTrades.reversed.take(5))
            _planLine('${trade.instrumentId} • ${trade.direction} • ${trade.reason}', '${trade.realizedPnl >= 0 ? '+' : ''}${(trade.realizedPnl - trade.fees).toStringAsFixed(2)} USDT net', trade.realizedPnl - trade.fees >= 0 ? _green : _red),
        ],
      ]),
    );
  }

  // ignore: unused_element
  Widget _universeCard() => _card(
    title: 'СКАНЕР РЫНКА • ВСЕ ДОСТУПНЫЕ ИНСТРУМЕНТЫ',
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('${_instruments.length} инструментов OKX • сортировка по 24h обороту', style: const TextStyle(color: _muted, fontSize: 11)),
      const SizedBox(height: 8),
      SizedBox(width: double.infinity, child: OutlinedButton.icon(
        onPressed: _showInstrumentPicker,
        icon: const Icon(Icons.tune),
        label: const Text('НАЙТИ МОНЕТУ / ИНСТРУМЕНТ'),
      )),
    ]),
  );


  Widget _planLine(String label, String value, [Color color = Colors.white]) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: Row(children: [
      Expanded(child: Text(label, style: const TextStyle(color: _muted, fontSize: 11))),
      Text(value, style: TextStyle(color: color, fontWeight: FontWeight.w600, fontSize: 12)),
    ]),
  );

  Widget _miniMetric(String label, String value, Color color) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    Text(label, style: const TextStyle(color: _muted, fontSize: 9)),
    const SizedBox(height: 3),
    Text(value, style: TextStyle(color: color, fontWeight: FontWeight.w600, fontSize: 11)),
  ]);

  Widget _card({String? title, required Widget child}) => Container(
    padding: const EdgeInsets.all(15),
    decoration: BoxDecoration(color: _panel, borderRadius: BorderRadius.circular(17), border: Border.all(color: Colors.white.withValues(alpha: 0.04))),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (title != null) ...[
        Text(title, style: const TextStyle(color: _muted, fontSize: 10, fontWeight: FontWeight.w700, letterSpacing: 1)),
        const SizedBox(height: 13),
      ],
      child,
    ]),
  );

  void _showInstrumentPicker() {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: _bg,
      builder: (context) => StatefulBuilder(builder: (context, modalSet) => SafeArea(
        child: SizedBox(
          height: MediaQuery.of(context).size.height * 0.82,
          child: Column(children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: TextField(
                controller: _search,
                autofocus: true,
                decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'BTC-USDT, ETH-USDT…'),
                onChanged: (_) => modalSet(() {}),
              ),
            ),
            Expanded(child: ListView.builder(
              itemCount: _filtered.length,
              itemBuilder: (context, index) {
                final item = _filtered[index];
                return ListTile(
                  title: Text(item.id),
                  subtitle: Text('24h turnover: ${item.turnover.toStringAsFixed(0)}'),
                  trailing: item.id == _selected?.id ? const Icon(Icons.check, color: _green) : null,
                  onTap: () => _selectInstrument(item),
                );
              },
            )),
          ]),
        ),
      )),
    ).whenComplete(() => _search.clear());
  }
}

class _ForecastPainter extends CustomPainter {
  _ForecastPainter(this.forecast);
  final MarketForecast forecast;
  @override
  void paint(Canvas canvas, Size size) {
    final pts=forecast.points; if(pts.isEmpty)return;
    const pad=12.0; final left=pad,right=size.width-pad,top=pad,bottom=size.height-pad;
    final values=<double>[forecast.currentPrice,...pts.expand((p)=>[p.lower,p.upper])];
    final lo=values.reduce((a,b)=>math.min(a,b).toDouble()),hi=values.reduce((a,b)=>math.max(a,b).toDouble()),range=math.max(hi-lo,hi.abs()*0.000001).toDouble();
    double y(double v)=>bottom-(v-lo)/range*(bottom-top); final dx=(right-left)/pts.length;
    final band=Path()..moveTo(left,y(pts.first.upper));
    for(var i=0;i<pts.length;i++)band.lineTo(left+dx*(i+1),y(pts[i].upper));
    for(var i=pts.length-1;i>=0;i--)band.lineTo(left+dx*(i+1),y(pts[i].lower));
    band.close();canvas.drawPath(band,Paint()..color=_blue.withValues(alpha:0.14));
    final median=Path()..moveTo(left,y(forecast.currentPrice));
    for(var i=0;i<pts.length;i++)median.lineTo(left+dx*(i+1),y(pts[i].median));
    canvas.drawPath(median,Paint()..color=_blue..style=PaintingStyle.stroke..strokeWidth=2.2);
    canvas.drawLine(Offset(left,y(forecast.currentPrice)),Offset(right,y(forecast.currentPrice)),Paint()..color=_muted.withValues(alpha:0.4));
    final label=TextPainter(text:TextSpan(text:'NOW ${forecast.currentPrice.toStringAsFixed(2)} → +${pts.length} bars',style:const TextStyle(color:_muted,fontSize:9)),textDirection:TextDirection.ltr)..layout();
    label.paint(canvas,Offset(left,0));
  }
  @override
  bool shouldRepaint(covariant _ForecastPainter oldDelegate)=>oldDelegate.forecast!=forecast;
}

class _CandlePainter extends CustomPainter {
  _CandlePainter(this.candles, {required this.forecast, required this.position});
  final List<MarketCandle> candles;
  final MarketForecast? forecast;
  final PaperPosition? position;

  @override
  void paint(Canvas canvas, Size size) {
    if (candles.length < 2) return;
    // Fewer, larger candles improve readability on a phone screen.
    final visible = candles.length > 48 ? candles.sublist(candles.length - 48) : candles;
    final projected = forecast?.points ?? const <ForecastPoint>[];
    final values = <double>[
      ...visible.expand((c) => [c.high, c.low]),
      if (projected.isNotEmpty) ...projected.map((p) => p.median),
      if (position != null) ...[position!.plan.entry, position!.effectiveStopLoss, position!.plan.takeProfit2],
    ];
    final minV = values.reduce((a, b) => math.min(a, b).toDouble());
    final maxV = values.reduce((a, b) => math.max(a, b).toDouble());
    final padding = (maxV - minV) * 0.08;
    final low = minV - padding, high = maxV + padding;
    final range = math.max(high - low, high.abs() * 0.00001).toDouble();
    const left = 5.0, right = 58.0, top = 7.0, bottom = 7.0;
    final plotWidth = size.width - left - right, plotHeight = size.height - top - bottom;
    double y(double price) => top + (high - price) / range * plotHeight;

    final futureWidth = projected.isEmpty ? 0.0 : plotWidth * 0.30;
    final candleWidth = plotWidth - futureWidth;
    final step = candleWidth / visible.length;
    final bodyWidth = math.max(2.6, step * 0.72).toDouble();
    for (var i = 0; i < visible.length; i++) {
      final candle = visible[i], x = left + step * (i + 0.5);
      final color = candle.close >= candle.open ? _green : _red;
      canvas.drawLine(Offset(x, y(candle.high)), Offset(x, y(candle.low)), Paint()..color = color..strokeWidth = 1);
      final bodyTop = y(math.max(candle.open, candle.close)), bodyBottom = y(math.min(candle.open, candle.close));
      canvas.drawRect(Rect.fromLTRB(x - bodyWidth / 2, bodyTop, x + bodyWidth / 2, math.max(bodyTop + 1.2, bodyBottom)), Paint()..color = color);
    }

    if (projected.isNotEmpty) {
      final startX = left + candleWidth, futureStep = futureWidth / projected.length;
      final band = Path();
      for (var i = 0; i < projected.length; i++) {
        final x = startX + futureStep * (i + 0.5);
        if (i == 0) band.moveTo(x, y(projected[i].upper)); else band.lineTo(x, y(projected[i].upper));
      }
      for (var i = projected.length - 1; i >= 0; i--) {
        band.lineTo(startX + futureStep * (i + 0.5), y(projected[i].lower));
      }
      band.close();
      canvas.drawPath(band, Paint()..color = _blue.withValues(alpha: .14));
      final path = Path()..moveTo(startX, y(visible.last.close));
      for (var i = 0; i < projected.length; i++) {
        path.lineTo(startX + futureStep * (i + 0.5), y(projected[i].median));
      }
      final rising = projected.last.median >= visible.last.close;
      canvas.drawPath(path, Paint()..color = (rising ? _green : _red)..style = PaintingStyle.stroke..strokeWidth = 2.2..strokeCap = StrokeCap.round);
      canvas.drawLine(Offset(startX, top), Offset(startX, size.height - bottom), Paint()..color = _muted.withValues(alpha: .55));
      final label = TextPainter(text: const TextSpan(text: 'ПРОГНОЗ', style: TextStyle(color: _blue, fontSize: 7, fontWeight: FontWeight.bold)), textDirection: TextDirection.ltr)..layout();
      label.paint(canvas, Offset(startX + 2, top + 1));
    }

    void drawLevel(double price, Color color, String label) {
      final yy = y(price);
      canvas.drawLine(Offset(left, yy), Offset(size.width - right, yy), Paint()..color = color.withValues(alpha: .9)..strokeWidth = 1.3);
      final tp = TextPainter(text: TextSpan(text: label, style: TextStyle(color: color, fontSize: 7, fontWeight: FontWeight.bold)), textDirection: TextDirection.ltr)..layout(maxWidth: right - 3);
      tp.paint(canvas, Offset(size.width - right + 3, (yy - 4).clamp(0.0, size.height - 9)));
    }
    if (position != null) {
      drawLevel(position!.plan.entry, _blue, 'ВХОД');
      drawLevel(position!.effectiveStopLoss, _red, 'SL');
      drawLevel(position!.plan.takeProfit2, _green, 'TP');
    }
  }

  @override
  bool shouldRepaint(covariant _CandlePainter old) =>
      old.candles != candles || old.forecast != forecast || old.position != position;
}
