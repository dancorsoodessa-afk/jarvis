import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'okx_market.dart';
import 'paper_trading.dart';
import 'signal_engine.dart';

void main() => runApp(const BotokApp());

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
  final _prices = <double>[];
  final _candles = <MarketCandle>[];
  final _search = TextEditingController();
  final _capital = TextEditingController(text: '1000');
  StreamSubscription<Map<String, dynamic>>? _feed;
  List<MarketInstrument> _instruments = [];
  MarketInstrument? _selected;
  String _marketType = 'SPOT';
  String _status = 'Загрузка рынка OKX…';
  double _price = 0;
  double _bid = 0;
  double _ask = 0;
  double _bookImbalance = 0;
  double _tradeDelta = 0;
  double _leverage = 1;
  double _riskPercent = 1;
  late PaperTradingEngine _paper;
  Future<void>? _paperRestore;
  bool _paperReady = false;
  DateTime _lastPaperPersist = DateTime.fromMillisecondsSinceEpoch(0);
  String _positionState = 'Нет открытой paper-позиции';
  bool _loading = false;
  bool _confirmMode = true;

  TradeSignal get _signal => calculateSignal(
    prices: _prices,
    bookImbalance: _bookImbalance,
    tradeDelta: _tradeDelta,
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
    _loadMarket();
    _search.addListener(() { if (mounted) setState(() {}); });
  }

  Future<void> _restorePaper() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = prefs.getString('botok.paper.wallet.v1');
      if (saved != null) _paper = PaperTradingEngine.decode(saved);
      if (_paper.openPosition != null) {
        _positionState = 'PAPER ${_paper.openPosition!.plan.direction} восстановлена • SL/TP активны';
      }
    } catch (e) {
      _positionState = 'Не удалось восстановить демо-кошелёк: $e';
    }
    if (mounted) setState(() => _paperReady = true);
  }

  Future<void> _persistPaper() async {
    _lastPaperPersist = DateTime.now();
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('botok.paper.wallet.v1', _paper.encode());
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
      final history = await _market.loadCandles(instrument.id, bar: '1m', limit: 100);
      _candles
        ..clear()
        ..addAll(history);
      if (history.isNotEmpty) _price = history.last.close;
    } catch (e) {
      if (mounted) setState(() => _status = 'Свечной архив OKX недоступен: $e');
    }
    await _market.watch(instrument.id);
    _prices
      ..clear()
      ..addAll(_candles.map((candle) => candle.close));
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
    if (type == 'candle1m') {
      for (final raw in rows) {
        try {
          final candle = MarketCandle.fromOkx(raw as List<dynamic>);
          final index = _candles.indexWhere((item) => item.timestamp == candle.timestamp);
          if (index >= 0) {
            _candles[index] = candle;
          } else {
            _candles.add(candle);
            if (_candles.length > 120) _candles.removeAt(0);
          }
        } catch (_) {}
      }
      _prices
        ..clear()
        ..addAll(_candles.map((candle) => candle.close));
      setState(() {});
      return;
    }
    final row = rows.first as Map<String, dynamic>;
    if (type == 'tickers') {
      final last = double.tryParse(row['last']?.toString() ?? '') ?? 0;
      if (last > 0) {
        _price = last;
        _prices.add(last);
        if (_prices.length > 160) _prices.removeAt(0);
        _managePaperPosition(last);
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
    }
    setState(() {});
  }

  void _managePaperPosition(double last) {
    final closed = _paper.markPrice(last);
    if (closed != null) {
      _positionState = 'PAPER закрыта: ${closed.reason} • NET ${(closed.realizedPnl - closed.fees).toStringAsFixed(2)} USDT';
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
    final signal = _signal;
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
    }
  }

  void _toast(String message) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  String _fmt(double value) => value >= 100 ? value.toStringAsFixed(2) : value.toStringAsFixed(5);

  @override
  void dispose() {
    _feed?.cancel();
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
              const SizedBox(height: 12),
              _walletCard(),
              const SizedBox(height: 12),
              _chartCard(),
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
    title: 'OKX • СВЕЧИ 1m • LONG / SHORT ЗОНЫ',
    child: SizedBox(height: 230, child: _candles.length < 2
      ? const Center(child: Text('Загрузка OHLC-свечей OKX…', style: TextStyle(color: _muted, fontSize: 12)))
      : CustomPaint(
          painter: _CandlePainter(
            List<MarketCandle>.from(_candles),
            forecastPrice: _price,
            position: _paper.openPosition,
          ),
          child: const SizedBox.expand(),
        )),
  );

  Widget _signalCard(TradeSignal signal) => _card(
    title: 'AI SIGNAL • LONG / SHORT',
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
      const Text('Вероятности — расчётная оценка модели, не гарантия исхода.', style: TextStyle(color: _muted, fontSize: 10)),
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
    final plan = _paperReady && _price > 0 && _paper.availableBalance > 0
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
    final pnlPercent = p == null || p.plan.entry * p.quantity == 0
      ? 0.0
      : pnl / (p.plan.entry * p.quantity) * 100;
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
          _planLine('Stop Loss', _fmt(p.plan.stopLoss), _red),
          _planLine('Take Profit 1 / 2', '${_fmt(p.plan.takeProfit1)} / ${_fmt(p.plan.takeProfit2)}', _green),
          _planLine('Текущий PnL', '${pnl >= 0 ? '+' : ''}${pnl.toStringAsFixed(2)} USDT  (${pnlPercent.toStringAsFixed(2)}%)', pnl >= 0 ? _green : _red),
          _planLine('TP1', p.takeProfit1Hit ? '50% зафиксировано' : 'ожидание'),
          SizedBox(width: double.infinity, child: OutlinedButton(
            onPressed: () async {
              final trade = _paper.closeManually();
              if (trade != null) {
                setState(() => _positionState = 'Закрыта вручную • NET ${(trade.realizedPnl - trade.fees).toStringAsFixed(2)} USDT');
                await _persistPaper();
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

class _CandlePainter extends CustomPainter {
  _CandlePainter(this.candles, {required this.forecastPrice, required this.position});
  final List<MarketCandle> candles;
  final double forecastPrice;
  final PaperPosition? position;

  @override
  void paint(Canvas canvas, Size size) {
    if (candles.length < 2) return;
    final last = forecastPrice > 0 ? forecastPrice : candles.last.close;
    final unit = last * 0.008;
    final levels = <({String label, double price, Color color})>[
      (label: 'LONG SL', price: last - unit, color: _red),
      (label: 'LONG TP1', price: last + unit * 1.5, color: _green),
      (label: 'LONG TP2', price: last + unit * 2.5, color: _green),
      (label: 'SHORT SL', price: last + unit, color: _red),
      (label: 'SHORT TP1', price: last - unit * 1.5, color: _red),
      (label: 'SHORT TP2', price: last - unit * 2.5, color: _green),
    ];
    final values = <double>[
      ...candles.expand((c) => [c.high, c.low]),
      ...levels.map((l) => l.price),
      if (position != null) ...[
        position!.plan.entry, position!.plan.stopLoss,
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

    final candleStep = plotWidth / candles.length;
    final bodyWidth = math.max(2.0, candleStep * 0.58).toDouble();
    for (var i = 0; i < candles.length; i++) {
      final candle = candles[i];
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
      drawLevel(position!.plan.stopLoss, _red, 'ACTIVE SL', solid: true);
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
