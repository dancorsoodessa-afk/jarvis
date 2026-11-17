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
  final _capital = TextEditingController(text: '1000');
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

  TradeSignal get _signal => _analysis.signal;

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
    _guardFeed = FlutterBackgroundService().on('paperUpdate').listen((event) {
      if (!mounted || event == null) return;
      final wallet = event['wallet'];
      if (wallet is! String) return;
      try {
        _paper = PaperTradingEngine.decode(wallet);
        final price = double.tryParse(event['price']?.toString() ?? '') ?? 0;
        if (price > 0) _price = price;
        final reason = event['closedReason'];
        _guardRunning = reason is! String || reason.isEmpty;
        if (reason is String && reason.isNotEmpty) {
          _positionState = 'PAPER закрыта фоновым контроллером: $reason';
          _guardStatus = 'позиция закрыта';
          stopPaperGuardService();
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
      _btcCandles.clear();
      final benchmarkId = instrument.id.endsWith('-SWAP') ? 'BTC-USDT-SWAP' : 'BTC-USDT';
      if (instrument.id != benchmarkId) {
        try { _btcCandles.addAll(await _market.loadCandles(benchmarkId, bar: '1m', limit: 300)); } catch (_) {}
      }
    } catch (e) {
      if (mounted) setState(() => _status = 'Свечной архив OKX недоступен: $e');
    }
    await _market.watch(instrument.id);
    _bookImbalance = 0;
    _tradeDelta = 0;
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
      setState(() => _status = 'Соединение закрыто — переподключите инструмент');
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
      if (last > 0) {
        _price = last;
        if (_paper.openPosition != null) _checkPaperGuard(last);
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
        if (item is! Map<String, dynamic>) continue;
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
    setState(() { _selected = instrument; _price = 0; _candles.clear(); });
    try {
      await _connectSelected();
    } catch (e) {
      if (mounted) setState(() => _status = 'Ошибка WebSocket: $e');
    }
  }

  Future<void> _openPaper() async {
    if (!_paperReady) { _toast('Демо-кошелёк ещё загружается.'); return; }
    if (_paper.openPosition != null) { _toast('Сначала закройте текущую PAPER-позицию.'); return; }
    if (_price <= 0) { _toast('Нет актуальной цены OKX'); return; }
    final analysis = _analysis;
    final signal = analysis.signal;
    if (!analysis.isAligned) {
      _toast('Сделка заблокирована: нужно минимум 3 активных таймфрейма и согласие направлений не ниже 60%.');
      return;
    }
    if (_marketType == 'SPOT' && signal.direction == 'SHORT') {
      _toast('SHORT нельзя открыть на спотовом рынке. Переключите рынок на SWAP.');
      return;
    }
    if (signal.confidence < 58) {
      _toast('Сигнал слабый: ${signal.confidence.toStringAsFixed(1)}%. Ожидание.');
      return;
    }
    late final TradePlan plan;
    try {
      plan = buildTradePlan(
        direction: signal.direction,
        entry: _price,
        capital: _paper.availableBalance,
        riskPercent: _riskPercent,
        leverage: _leverage,
      );
    } catch (e) {
      _toast('Не удалось рассчитать сделку: $e');
      return;
    }
    if (_confirmMode) {
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
      setState(() => _positionState = 'PAPER ${plan.direction} • SL/TP активны');
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

  void _toast(String message) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  String _fmt(double value) => value >= 100 ? value.toStringAsFixed(2) : value.toStringAsFixed(5);

  @override
  void dispose() {
    _feed?.cancel();
    _guardFeed?.cancel();
    _guardStatusFeed?.cancel();
    _guardErrorFeed?.cancel();
    _guardStoppedFeed?.cancel();
    _market.dispose();
    _search.dispose();
    _capital.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final selected = _selected;
    final signal = _signal;
    return Scaffold(
      appBar: AppBar(
        backgroundColor: _bg,
        title: const Row(children: [
          Icon(Icons.auto_graph_rounded, color: _blue),
          SizedBox(width: 9),
          Text('BOTok', style: TextStyle(fontWeight: FontWeight.w800, letterSpacing: 1.2)),
          SizedBox(width: 8),
          Text('OKX AI TRADER', style: TextStyle(fontSize: 10, color: _muted)),
        ]),
        actions: [
          IconButton(onPressed: _loading ? null : _loadMarket, icon: const Icon(Icons.refresh)),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _loadMarket,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 28),
            children: [
              _statusBar(),
              const SizedBox(height: 14),
              _marketSelector(),
              const SizedBox(height: 12),
              _instrumentCard(selected),
              if (_marketType == 'SWAP') ...[
                const SizedBox(height: 12),
                _derivativesFeedCard(),
              ],
              const SizedBox(height: 12),
              _walletCard(),
              const SizedBox(height: 12),
              _chartCard(),
              const SizedBox(height: 12),
              _forecastCard(),
              const SizedBox(height: 12),
              _timeframeConfluenceCard(),
              if (_btcCandles.isNotEmpty && selected?.id != 'BTC-USDT' && selected?.id != 'BTC-USDT-SWAP') ...[
                const SizedBox(height: 12),
                _btcCorrelationCard(),
              ],
              const SizedBox(height: 12),
              _backtestCard(),
              const SizedBox(height: 12),
              _signalCard(signal),
              const SizedBox(height: 12),
              _tradePlanCard(signal),
              const SizedBox(height: 12),
              _paperCard(),
              const SizedBox(height: 12),
              _universeCard(),
              const SizedBox(height: 12),
              const Text('Источники: публичный OKX API • обновления WebSocket', style: TextStyle(color: _muted, fontSize: 11)),
              const SizedBox(height: 5),
              const Text('Только Paper Trading. Реальные ордера и ключи OKX не используются.', style: TextStyle(color: _muted, fontSize: 11)),
            ],
          ),
        ),
      ),
    );
  }



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
            painter: _CandlePainter(List<MarketCandle>.from(_candles), forecastPrice: _price, position: _paper.openPosition),
            child: const SizedBox.expand(),
          )),
    ]),
  );

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
  _CandlePainter(this.candles, {required this.forecastPrice, required this.position});
  final List<MarketCandle> candles;
  final double forecastPrice;
  final PaperPosition? position;

  @override
  void paint(Canvas canvas, Size size) {
    if (candles.length < 2) return;
    final visibleCandles = candles.length > 160
        ? candles.sublist(candles.length - 160)
        : candles;
    final last = forecastPrice > 0 ? forecastPrice : visibleCandles.last.close;
    final unit = last * 0.008;
    final levels = <({String label, double price, Color color})>[
      (label: 'LONG SL', price: last - unit, color: _red),
      (label: 'LONG TP1', price: last + unit * 1.5, color: _green),
      (label: 'LONG TP2', price: last + unit * 2.5, color: _green),
      (label: 'SHORT SL', price: last + unit, color: _red),
      (label: 'SHORT TP1', price: last - unit * 1.5, color: _green),
      (label: 'SHORT TP2', price: last - unit * 2.5, color: _green),
    ];
    final values = <double>[
      ...visibleCandles.expand((c) => [c.high, c.low]),
      ...levels.map((l) => l.price),
      if (position != null) ...[
        position!.plan.entry, position!.effectiveStopLoss,
        position!.plan.takeProfit1, position!.plan.takeProfit2,
      ],
    ];
    final minV = values.reduce((a, b) => math.min(a, b).toDouble());
    final maxV = values.reduce((a, b) => math.max(a, b).toDouble());
    final range = math.max(maxV - minV, maxV.abs() * 0.00001).toDouble();
    const left = 5.0;
    const right = 72.0;
    const top = 8.0;
    const bottom = 8.0;
    final plotWidth = size.width - left - right;
    final plotHeight = size.height - top - bottom;
    double y(double price) => top + (maxV - price) / range * plotHeight;

    final candleStep = plotWidth / visibleCandles.length;
    final bodyWidth = math.max(2.0, candleStep * 0.58).toDouble();
    for (var i = 0; i < visibleCandles.length; i++) {
      final candle = visibleCandles[i];
      final x = left + candleStep * (i + 0.5);
      final rising = candle.close >= candle.open;
      final color = rising ? _green : _red;
      final wick = Paint()..color = color..strokeWidth = 1.2;
      canvas.drawLine(Offset(x, y(candle.high)), Offset(x, y(candle.low)), wick);
      final bodyTop = y(math.max(candle.open, candle.close).toDouble());
      final bodyBottom = y(math.min(candle.open, candle.close).toDouble());
      final rect = Rect.fromLTRB(
        x - bodyWidth / 2, bodyTop, x + bodyWidth / 2,
        math.max(bodyTop + 1.5, bodyBottom).toDouble(),
      );
      canvas.drawRect(rect, Paint()..color = color);
    }

    void drawLevel(double price, Color color, String label, {bool solid = false}) {
      final yy = y(price);
      final paint = Paint()
        ..color = color.withValues(alpha: 0.85)
        ..strokeWidth = solid ? 1.7 : 1;
      final xEnd = size.width - right + 2;
      if (solid) {
        canvas.drawLine(Offset(left, yy), Offset(xEnd, yy), paint);
      } else {
        const dash = 4.0;
        var x = left;
        while (x < xEnd) {
          canvas.drawLine(Offset(x, yy), Offset(math.min(x + dash, xEnd).toDouble(), yy), paint);
          x += dash * 2;
        }
      }
      final text = TextPainter(
        text: TextSpan(
          text: '$label ${price.toStringAsFixed(price >= 100 ? 1 : 4)}',
          style: TextStyle(color: color, fontSize: 7, fontWeight: FontWeight.w600),
        ),
        textDirection: TextDirection.ltr,
        maxLines: 1,
      )..layout(maxWidth: right - 4);
      text.paint(canvas, Offset(size.width - right + 5, (yy - 5).clamp(0.0, size.height - 10).toDouble()));
    }

    for (final level in levels) {
      drawLevel(level.price, level.color, level.label);
    }
    if (position != null) {
      drawLevel(position!.plan.entry, _blue, 'ENTRY', solid: true);
      drawLevel(position!.effectiveStopLoss, _red, 'ACTIVE SL', solid: true);
      if (position!.trailingStopPrice != null) {
        drawLevel(position!.trailingStopPrice!, _blue, 'TRAILING SL', solid: true);
      }
      drawLevel(position!.plan.takeProfit1, _green, 'ACTIVE TP1', solid: true);
      drawLevel(position!.plan.takeProfit2, _green, 'ACTIVE TP2', solid: true);
    }
  }

  @override
  bool shouldRepaint(covariant _CandlePainter oldDelegate) =>
      oldDelegate.candles != candles ||
      oldDelegate.forecastPrice != forecastPrice ||
      oldDelegate.position != position;
}
