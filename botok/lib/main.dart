import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'okx_market.dart';
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
  final _search = TextEditingController();
  final _capital = TextEditingController(text: '100');
  final _allocation = TextEditingController(text: '10');
  final _targetNet = TextEditingController(text: '1.0');
  List<MarketCandle> _candles = [];
  String _bar = '5m';
  Timer? _candleRefresh;
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
  AllocationPlan? _paperPosition;
  String _positionState = 'Нет открытой paper-позиции';
  bool _loading = false;
  bool _confirmMode = true;
  bool _autoCycleEnabled = false;
  bool _cycleRunning = false;
  Timer? _cycleRetry;

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
    _loadMarket();
    _search.addListener(() { if (mounted) setState(() {}); });
  }

  Future<void> _loadMarket() async {
    setState(() { _loading = true; _status = 'Получаем инструменты OKX…'; });
    try {
      final items = await _market.loadInstruments(_marketType);
      if (!mounted) return;
      setState(() {
        _instruments = items;
        _selected = items.firstWhere(
          (i) => i.id == (_marketType == 'SPOT' ? 'BTC-USDT' : 'BTC-USDT-SWAP'),
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
    await _market.watch(instrument.id);
    await _refreshCandles();
    _candleRefresh?.cancel();
    _cycleRetry?.cancel();
    _candleRefresh = Timer.periodic(const Duration(seconds: 20), (_) => _refreshCandles());
    _bookImbalance = 0;
    _tradeDelta = 0;
    _feed = _market.events.listen(_onMarketEvent);
    if (mounted) setState(() => _status = 'LIVE • ${instrument.id}');
  }

  Future<void> _refreshCandles() async {
    final instrument = _selected;
    if (instrument == null) return;
    try {
      final data = await _market.loadCandles(instrument.id, bar: _bar, limit: 100);
      if (mounted) setState(() {
        _candles = data;
        if (data.isNotEmpty) _price = data.last.close;
        _prices..clear()..addAll(data.map((c) => c.close));
      });
    } catch (e) {
      if (mounted) setState(() => _status = 'Свечи: $e');
    }
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
    final position = _paperPosition;
    if (position == null) return;
    final isLong = position.direction == 'LONG';
    if ((isLong && last <= position.stopLoss) || (!isLong && last >= position.stopLoss)) {
      _paperPosition = null;
      _positionState = 'PAPER закрыта по Stop Loss • ${_fmt(last)}';
      if (_autoCycleEnabled) Future.microtask(_scanNextOpportunity);
    } else if ((isLong && last >= position.takeProfit) || (!isLong && last <= position.takeProfit)) {
      _paperPosition = null;
      _positionState = 'PAPER закрыта по чистой целевой прибыли • ${_fmt(last)}';
      if (_autoCycleEnabled) Future.microtask(_scanNextOpportunity);
    }
  }

  Future<void> _switchMarket(String type) async {
    if (_marketType == type) return;
    setState(() { _marketType = type; _selected = null; _paperPosition = null; _candles = []; });
    await _market.disconnect();
    await _loadMarket();
  }

  Future<void> _selectInstrument(MarketInstrument instrument) async {
    Navigator.pop(context);
    setState(() { _selected = instrument; _price = 0; _paperPosition = null; });
    try {
      await _connectSelected();
    } catch (e) {
      if (mounted) setState(() => _status = 'Ошибка WebSocket: $e');
    }
  }

  Future<void> _scanNextOpportunity() async {
    if (!_autoCycleEnabled || _cycleRunning || _paperPosition != null) return;
    _cycleRunning = true;
    if (mounted) setState(() => _status = 'АГЕНТ: сканирование лучших пар по ликвидности и свечным сигналам…');
    try {
      MarketInstrument? best;
      var bestScore = 0.0;
      final candidates = _instruments.take(24).toList();
      for (final instrument in candidates) {
        if (!_autoCycleEnabled || _paperPosition != null) break;
        try {
          final candles = await _market.loadCandles(instrument.id, bar: _bar, limit: 80);
          if (candles.length < 30) continue;
          final signal = calculateSignal(prices: candles.map((c) => c.close).toList());
          if (_marketType == 'SPOT' && signal.direction != 'LONG') continue;
          final score = signal.confidence;
          if (score > bestScore) {
            bestScore = score;
            best = instrument;
          }
        } catch (_) {
          // Continue scanning when one instrument has unavailable candle data.
        }
      }
      if (best != null && bestScore >= 60 && _autoCycleEnabled && _paperPosition == null) {
        if (mounted) setState(() {
          _selected = best;
          _status = 'АГЕНТ: выбрана ${best!.id} • оценка ${bestScore.toStringAsFixed(1)}%';
        });
        await _connectSelected();
        if (_autoCycleEnabled && _paperPosition == null && _signal.confidence >= 58) {
          await _openPaper();
        }
      } else if (mounted && _autoCycleEnabled) {
        setState(() => _status = 'АГЕНТ: подходящей пары пока нет • повторный поиск через 20 сек');
        _cycleRetry?.cancel();
        _cycleRetry = Timer(const Duration(seconds: 20), _scanNextOpportunity);
      }
    } finally {
      _cycleRunning = false;
    }
  }

  Future<void> _openPaper() async {
    if (_price <= 0) { _toast('Нет актуальной цены OKX'); return; }
    final signal = _signal;
    if (_marketType == 'SPOT' && signal.direction == 'SHORT') {
      _toast('Spot не поддерживает открытие SHORT. Агент продолжит поиск LONG.');
      if (_autoCycleEnabled) { _cycleRetry?.cancel(); _cycleRetry = Timer(const Duration(seconds: 20), _scanNextOpportunity); }
      return;
    }
    if (signal.confidence < 58) {
      _toast('Сигнал слабый: ${signal.confidence.toStringAsFixed(1)}%. Ожидание.');
      if (_autoCycleEnabled) { _cycleRetry?.cancel(); _cycleRetry = Timer(const Duration(seconds: 20), _scanNextOpportunity); }
      return;
    }
    final plan = _tryAllocationPlan(signal.direction);
    if (plan == null) { _toast('Проверь баланс, процент и чистую цель.'); if (_autoCycleEnabled) { _cycleRetry?.cancel(); _cycleRetry = Timer(const Duration(seconds: 20), _scanNextOpportunity); } return; }
    if (_confirmMode) {
      final approved = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          backgroundColor: _panel,
          title: const Text('Подтвердить PAPER-сделку?'),
          content: Text('${plan.direction} • ${_selected?.id}\nВход: ${_fmt(plan.entry)}\nОбъём: ${plan.notional.toStringAsFixed(2)} USDT\nSL: ${_fmt(plan.stopLoss)}\nВыход для чистой цели: ${_fmt(plan.takeProfit)}\nЧистая прибыль: ${plan.netTarget.toStringAsFixed(4)} USDT'),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Отмена')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Подтвердить')),
          ],
        ),
      );
      if (approved != true) return;
    }
    setState(() {
      _paperPosition = plan;
      _positionState = 'PAPER ${plan.direction} • цель рассчитана после комиссий';
    });
  }

  void _toast(String message) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  String _fmt(double value) => value >= 100 ? value.toStringAsFixed(2) : value.toStringAsFixed(5);

  @override
  void dispose() {
    _feed?.cancel();
    _candleRefresh?.cancel();
    _market.dispose();
    _search.dispose();
    _capital.dispose();
    _allocation.dispose();
    _targetNet.dispose();
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
    title: 'СВЕЧНОЙ ГРАФИК • OHLCV + EMA 9/21',
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: 5, children: [
        for (final tf in ['1m', '5m', '15m', '1H', '4H', '1D'])
          ChoiceChip(
            label: Text(tf, style: const TextStyle(fontSize: 10)),
            selected: _bar.toLowerCase() == tf.toLowerCase(),
            onSelected: (_) {
              setState(() => _bar = tf == '1H' ? '1H' : (tf == '4H' ? '4H' : (tf == '1D' ? '1D' : tf)));
              _refreshCandles();
            },
            visualDensity: VisualDensity.compact,
          ),
      ]),
      const SizedBox(height: 8),
      SizedBox(
        height: 260,
        child: _candles.length < 5
          ? const Center(child: Text('Загрузка свечей OKX…', style: TextStyle(color: _muted)))
          : CustomPaint(painter: _CandlePainter(List<MarketCandle>.from(_candles)), child: const SizedBox.expand()),
      ),
      const SizedBox(height: 7),
      Row(children: [
        _miniMetric('EMA 9', _candles.length >= 9 ? _fmt(_chartEma(9)) : '—', _blue),
        const SizedBox(width: 18),
        _miniMetric('EMA 21', _candles.length >= 21 ? _fmt(_chartEma(21)) : '—', Colors.orange),
        const SizedBox(width: 18),
        _miniMetric('RSI 14', _candles.length >= 15 ? _chartRsi().toStringAsFixed(1) : '—', Colors.white),
      ]),
      const SizedBox(height: 5),
      const Text('Зелёная свеча — рост • красная — падение • линии — EMA 9/21', style: TextStyle(color: _muted, fontSize: 10)),
    ]),
  );

  double _chartEma(int period) {
    final closes = _candles.map((c) => c.close).toList();
    final k = 2 / (period + 1);
    var value = closes.first;
    for (final close in closes.skip(1)) { value = close * k + value * (1 - k); }
    return value;
  }

  double _chartRsi() {
    final closes = _candles.map((c) => c.close).toList();
    var gains = 0.0, losses = 0.0;
    for (var i = math.max(1, closes.length - 14).toInt(); i < closes.length; i++) {
      final d = closes[i] - closes[i - 1];
      if (d >= 0) { gains += d; } else { losses -= d; }
    }
    if (losses == 0) return gains == 0 ? 50 : 100;
    return 100 - 100 / (1 + gains / losses);
  }

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
    final plan = _price > 0 ? _tryAllocationPlan(signal.direction) : null;
    return _card(
      title: 'АВТОНОМНЫЙ РАСЧЁТ СДЕЛКИ',
      child: Column(children: [
        TextField(controller: _capital, keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(labelText: 'Баланс USDT'), onChanged: (_) => setState(() {})),
        const SizedBox(height: 9),
        Row(children: [
          Expanded(child: TextField(controller: _allocation, keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'Объём, % баланса'), onChanged: (_) => setState(() {}))),
          const SizedBox(width: 10),
          Expanded(child: TextField(controller: _targetNet, keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'Чистая цель, %'), onChanged: (_) => setState(() {}))),
        ]),
        if (plan != null) ...[
          _planLine('Направление', plan.direction, plan.direction == 'LONG' ? _green : _red),
          _planLine('Вход', _fmt(plan.entry)),
          _planLine('Объём позиции', '${plan.notional.toStringAsFixed(2)} USDT'),
          _planLine('Задействовано', '${plan.marginUsed.toStringAsFixed(2)} USDT'),
          _planLine('Количество', plan.quantity.toStringAsFixed(6)),
          _planLine('Stop Loss', _fmt(plan.stopLoss), _red),
          _planLine('Цена выхода для чистой цели', _fmt(plan.takeProfit), _green),
          _planLine('Комиссии вход + выход', '${plan.feesEstimate.toStringAsFixed(4)} USDT'),
          _planLine('Чистая прибыль', '${plan.netTarget.toStringAsFixed(4)} USDT', _green),
        ] else
          const Text('Введите баланс, процент капитала и чистую целевую прибыль.', style: TextStyle(color: _muted, fontSize: 11)),
        SwitchListTile(contentPadding: EdgeInsets.zero,
          title: const Text('Автоцикл: поиск → вход → чистая цель → следующий поиск', style: TextStyle(fontSize: 12)),
          subtitle: const Text('Автоматически только в PAPER; Spot открывает только LONG.', style: TextStyle(color: _muted, fontSize: 10)),
          value: _autoCycleEnabled,
          onChanged: (v) {
            setState(() { _autoCycleEnabled = v; if (v) _confirmMode = false; });
            _cycleRetry?.cancel();
            if (v) _scanNextOpportunity();
          }),
        SwitchListTile(contentPadding: EdgeInsets.zero,
          title: const Text('Подтверждение каждой сделки', style: TextStyle(fontSize: 12)),
          value: _confirmMode, onChanged: (v) => setState(() => _confirmMode = v)),
        SizedBox(width: double.infinity, child: FilledButton.icon(
          onPressed: _paperPosition == null ? _openPaper : null,
          icon: const Icon(Icons.play_arrow), label: const Text('ОТКРЫТЬ PAPER-СДЕЛКУ'))),
      ]),
    );
  }

  AllocationPlan? _tryAllocationPlan(String direction) {
    try {
      return buildAllocationPlan(
        direction: direction,
        entry: _price,
        quoteBalance: double.parse(_capital.text.replaceAll(',', '.')),
        allocationPercent: double.parse(_allocation.text.replaceAll(',', '.')),
        targetNetPercent: double.parse(_targetNet.text.replaceAll(',', '.')),
        leverage: _marketType == 'SPOT' ? 1 : _leverage,
      );
    } catch (_) { return null; }
  }

  Widget _paperCard() => _card(
    title: 'PAPER TRADING',
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(_positionState, style: const TextStyle(fontSize: 12, color: _muted)),
      if (_paperPosition case final p?) ...[
        const SizedBox(height: 8),
        _planLine('Направление', p.direction, p.direction == 'LONG' ? _green : _red),
        _planLine('SL / чистая цель', '${_fmt(p.stopLoss)} / ${_fmt(p.takeProfit)}'),
        SizedBox(width: double.infinity, child: OutlinedButton(
          onPressed: () { setState(() { _paperPosition = null; _positionState = 'PAPER позиция закрыта вручную'; }); if (_autoCycleEnabled) _scanNextOpportunity(); },
          child: const Text('ЗАКРЫТЬ PAPER-ПОЗИЦИЮ'),
        )),
      ],
    ]),
  );

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
  _CandlePainter(this.candles);
  final List<MarketCandle> candles;

  @override
  void paint(Canvas canvas, Size size) {
    if (candles.isEmpty) return;
    const left = 8.0, right = 58.0, top = 10.0, bottom = 18.0;
    final plot = Rect.fromLTRB(left, top, size.width - right, size.height - bottom);
    final minPrice = candles.map((c) => c.low).reduce((a, b) => math.min(a, b).toDouble());
    final maxPrice = candles.map((c) => c.high).reduce((a, b) => math.max(a, b).toDouble());
    final range = math.max(maxPrice - minPrice, maxPrice.abs() * 0.0001).toDouble();
    double y(double p) => plot.bottom - ((p - minPrice) / range) * plot.height;
    final grid = Paint()..color = Colors.white.withValues(alpha: .10)..strokeWidth = 1;
    const textStyle = TextStyle(color: Color(0xFF9AA9BD), fontSize: 9);
    for (var i = 0; i <= 4; i++) {
      final gy = plot.top + plot.height * i / 4;
      canvas.drawLine(Offset(plot.left, gy), Offset(plot.right, gy), grid);
      final value = maxPrice - range * i / 4;
      final tp = TextPainter(text: TextSpan(text: value.toStringAsFixed(value >= 100 ? 2 : 5), style: textStyle), textDirection: TextDirection.ltr)..layout(maxWidth: right - 4);
      tp.paint(canvas, Offset(plot.right + 5, gy - 6));
    }
    final slot = plot.width / candles.length;
    final bodyWidth = math.max(2.0, slot * .62).toDouble();
    final wick = Paint()..strokeWidth = 1.2;
    for (var i = 0; i < candles.length; i++) {
      final c = candles[i];
      final x = plot.left + slot * (i + .5);
      final rising = c.close >= c.open;
      final color = rising ? const Color(0xFF20D6A0) : const Color(0xFFFF647C);
      wick.color = color;
      canvas.drawLine(Offset(x, y(c.high)), Offset(x, y(c.low)), wick);
      final topY = math.min(y(c.open), y(c.close)).toDouble();
      final bottomY = math.max(y(c.open), y(c.close)).toDouble();
      final rect = Rect.fromLTRB(x - bodyWidth / 2, topY, x + bodyWidth / 2, math.max(topY + 1.5, bottomY).toDouble());
      canvas.drawRect(rect, Paint()..color = color);
    }
    void drawEma(int period, Color color) {
      if (candles.length < period) return;
      final k = 2 / (period + 1);
      var ema = candles.first.close;
      final path = Path();
      for (var i = 0; i < candles.length; i++) {
        ema = i == 0 ? candles[i].close : candles[i].close * k + ema * (1 - k);
        final x = plot.left + slot * (i + .5);
        if (i == 0) { path.moveTo(x, y(ema)); } else { path.lineTo(x, y(ema)); }
      }
      canvas.drawPath(path, Paint()..color = color..strokeWidth = 1.7..style = PaintingStyle.stroke);
    }
    drawEma(9, const Color(0xFF65A7FF));
    drawEma(21, const Color(0xFFFFC857));
    final last = candles.last.close;
    final ly = y(last);
    canvas.drawLine(Offset(plot.left, ly), Offset(plot.right, ly), Paint()..color = Colors.white54..strokeWidth = .8);
    final label = TextPainter(text: TextSpan(text: last.toStringAsFixed(last >= 100 ? 2 : 5), style: const TextStyle(color: Colors.white, fontSize: 9, fontWeight: FontWeight.bold)), textDirection: TextDirection.ltr)..layout();
    label.paint(canvas, Offset(plot.right + 4, ly - 14));
  }

  @override
  bool shouldRepaint(covariant _CandlePainter oldDelegate) => oldDelegate.candles != candles;
}
