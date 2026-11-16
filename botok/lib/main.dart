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
  StreamSubscription<Map<String, dynamic>>? _feed;
  List<MarketInstrument> _instruments = [];
  MarketInstrument? _selected;
  String _marketType = 'SPOT';
  String _status = 'Загрузка рынка OKX…';
  double _price = 0;
  double _change24 = 0;
  double _bid = 0;
  double _ask = 0;
  double _bookImbalance = 0;
  double _tradeDelta = 0;
  double _leverage = 1;
  double _riskPercent = 1;
  TradePlan? _paperPosition;
  String _positionState = 'Нет открытой paper-позиции';
  bool _loading = false;
  bool _confirmMode = true;
  bool _disposed = false;

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
    _prices.clear();
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
    final row = rows.first as Map<String, dynamic>;
    if (type == 'tickers') {
      final last = double.tryParse(row['last']?.toString() ?? '') ?? 0;
      if (last > 0) {
        _price = last;
        _change24 = double.tryParse(row['sodUtc8']?.toString() ?? '') == null
            ? _change24 : _change24;
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
      _tradeDelta = (_tradeDelta * 0.85 + (side == 'buy' ? 1 : -1) * (size / (size + 1)) * 0.15).clamp(-1.0, 1.0);
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
    } else if ((isLong && last >= position.takeProfit2) || (!isLong && last <= position.takeProfit2)) {
      _paperPosition = null;
      _positionState = 'PAPER закрыта по Take Profit 2 • ${_fmt(last)}';
    } else if ((isLong && last >= position.takeProfit1) || (!isLong && last <= position.takeProfit1)) {
      _positionState = 'PAPER: достигнут Take Profit 1 • контроль позиции';
    }
  }

  Future<void> _switchMarket(String type) async {
    if (_marketType == type) return;
    setState(() { _marketType = type; _selected = null; _paperPosition = null; });
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

  Future<void> _openPaper() async {
    if (_price <= 0) {
      _toast('Нет актуальной цены OKX');
      return;
    }
    final signal = _signal;
    final direction = signal.direction;
    final probability = signal.confidence;
    if (probability < 58) {
      _toast('Сигнал слабый: ${probability.toStringAsFixed(1)}%. Ожидание.');
      return;
    }
    final capital = double.tryParse(_capital.text.replaceAll(',', '.')) ?? 0;
    late final TradePlan plan;
    try {
      plan = buildTradePlan(
        direction: direction,
        entry: _price,
        capital: capital,
        riskPercent: _riskPercent,
        leverage: _leverage,
      );
    } catch (e) {
      _toast('Проверьте капитал: $e');
      return;
    }
    if (_confirmMode) {
      final approved = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          backgroundColor: _panel,
          title: const Text('Подтвердить PAPER-сделку?'),
          content: Text('${plan.direction}\nВход: ${_fmt(plan.entry)}\nStop Loss: ${_fmt(plan.stopLoss)}\nTP1: ${_fmt(plan.takeProfit1)}\nTP2: ${_fmt(plan.takeProfit2)}\nРиск: $${plan.riskAmount.toStringAsFixed(2)}'),
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
      _positionState = 'PAPER ${plan.direction} • SL/TP установлены автоматически';
    });
  }

  void _toast(String message) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  String _fmt(double value) => value >= 100 ? value.toStringAsFixed(2) : value.toStringAsFixed(5);

  @override
  void dispose() {
    _disposed = true;
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
    title: 'График цены • live',
    child: SizedBox(height: 170, child: _prices.length < 2
      ? const Center(child: Text('Ожидание рыночных данных…', style: TextStyle(color: _muted, fontSize: 12)))
      : CustomPaint(painter: _PricePainter(List<double>.from(_prices)), child: const SizedBox.expand())),
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
    final plan = _price > 0 && _capital.text.isNotEmpty
      ? _tryPlan(signal.direction)
      : null;
    return _card(
      title: 'ПЛАН СДЕЛКИ • АВТОРАСЧЁТ',
      child: Column(children: [
        TextField(
          controller: _capital,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(labelText: 'Капитал (USDT)', prefixIcon: Icon(Icons.account_balance_wallet_outlined)),
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: Text('Риск на сделку: ${_riskPercent.toStringAsFixed(1)}%', style: const TextStyle(fontSize: 12))),
          Expanded(child: Text('Плечо: ${_leverage.toStringAsFixed(0)}x', textAlign: TextAlign.end, style: const TextStyle(fontSize: 12))),
        ]),
        Row(children: [
          Expanded(child: Slider(value: _riskPercent, min: 0.25, max: 3, divisions: 11, onChanged: (v) => setState(() => _riskPercent = v))),
          Expanded(child: Slider(value: _leverage, min: 1, max: 20, divisions: 19, onChanged: (v) => setState(() => _leverage = v))),
        ]),
        if (plan != null) ...[
          _planLine('Направление', plan.direction, plan.direction == 'LONG' ? _green : _red),
          _planLine('Вход', _fmt(plan.entry)),
          _planLine('Stop Loss', _fmt(plan.stopLoss), _red),
          _planLine('Take Profit 1', _fmt(plan.takeProfit1), _green),
          _planLine('Take Profit 2', _fmt(plan.takeProfit2), _green),
          _planLine('Размер позиции', '${plan.quantity.toStringAsFixed(6)} ${selectedBase()}'),
          _planLine('Макс. риск', '$${plan.riskAmount.toStringAsFixed(2)}'),
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
          onPressed: _paperPosition == null ? _openPaper : null,
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
        capital: double.parse(_capital.text.replaceAll(',', '.')),
        riskPercent: _riskPercent,
        leverage: _leverage,
      );
    } catch (_) { return null; }
  }

  String selectedBase() => _selected?.base ?? 'coin';

  Widget _paperCard() => _card(
    title: 'PAPER TRADING',
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(_positionState, style: const TextStyle(fontSize: 12, color: _muted)),
      if (_paperPosition case final p?) ...[
        const SizedBox(height: 8),
        _planLine('Направление', p.direction, p.direction == 'LONG' ? _green : _red),
        _planLine('SL / TP2', '${_fmt(p.stopLoss)} / ${_fmt(p.takeProfit2)}'),
        SizedBox(width: double.infinity, child: OutlinedButton(
          onPressed: () => setState(() { _paperPosition = null; _positionState = 'PAPER позиция закрыта вручную'; }),
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

  String _fmtQty(double v) => v.toStringAsFixed(2);

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

class _PricePainter extends CustomPainter {
  _PricePainter(this.values);
  final List<double> values;

  @override
  void paint(Canvas canvas, Size size) {
    if (values.length < 2) return;
    final minV = values.reduce(math.min);
    final maxV = values.reduce(math.max);
    final range = math.max(maxV - minV, maxV.abs() * 0.00001);
    final path = Path();
    for (var i = 0; i < values.length; i++) {
      final x = size.width * i / (values.length - 1);
      final y = size.height - ((values[i] - minV) / range * (size.height - 18)) - 9;
      if (i == 0) { path.moveTo(x, y); } else { path.lineTo(x, y); }
    }
    final fill = Path.from(path)..lineTo(size.width, size.height)..lineTo(0, size.height)..close();
    canvas.drawPath(fill, Paint()..shader = LinearGradient(
      colors: [_blue.withValues(alpha: 0.28), _blue.withValues(alpha: 0.01)],
      begin: Alignment.topCenter, end: Alignment.bottomCenter,
    ).createShader(Offset.zero & size));
    canvas.drawPath(path, Paint()
      ..color = _blue
      ..strokeWidth = 2.2
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round);
  }

  @override
  bool shouldRepaint(covariant _PricePainter oldDelegate) => oldDelegate.values != values;
}
