import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'crypto_tools.dart';

const _chartCyan = Color(0xFF37D5EE);
const _chartPanel = Color(0xFF0B1420);

/// Always-visible market chart for the JARVIS home screen.
/// Signals/levels are analytical estimates, never exchange order confirmations.
class JarvisTradingChartPanel extends StatefulWidget {
  const JarvisTradingChartPanel({super.key});
  @override
  State<JarvisTradingChartPanel> createState() => _JarvisTradingChartPanelState();
}

class _JarvisTradingChartPanelState extends State<JarvisTradingChartPanel> {
  String _symbol = 'BTC-USDT';
  String _timeframe = '15m';
  bool _loading = false;
  String? _error;
  List<List<dynamic>> _candles = const [];
  DateTime? _updated;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _refresh());
  }

  Future<void> _refresh() async {
    if (_loading) return;
    setState(() { _loading = true; _error = null; });
    try {
      final data = await JarvisCrypto.candles(symbol: _symbol, timeframe: _timeframe, limit: 80);
      if (data.isEmpty) throw StateError('OKX не вернул свечи');
      if (!mounted) return;
      setState(() { _candles = data; _updated = DateTime.now(); });
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  double _n(List<dynamic> row, int index) =>
      index < row.length ? (double.tryParse(row[index].toString()) ?? 0) : 0;

  @override
  Widget build(BuildContext context) {
    final rows = _candles.reversed.toList();
    final closes = rows.map((r) => _n(r, 4)).where((v) => v > 0).toList();
    final last = closes.isEmpty ? 0.0 : closes.last;
    final sma20 = closes.length >= 20
        ? closes.skip(closes.length - 20).reduce((a, b) => a + b) / 20
        : null;
    final sma50 = closes.length >= 50
        ? closes.skip(closes.length - 50).reduce((a, b) => a + b) / 50
        : null;
    final rsi = _rsi(closes);
    final longSignal = sma20 != null && sma50 != null && sma20 > sma50 && (rsi == null || (rsi >= 45 && rsi < 70));
    final shortSignal = sma20 != null && sma50 != null && sma20 < sma50 && (rsi == null || (rsi > 30 && rsi <= 55));
    final signal = longSignal ? 'LONG' : shortSignal ? 'SHORT' : 'ОЖИДАНИЕ';
    final signalColor = longSignal ? Colors.greenAccent : shortSignal ? Colors.redAccent : Colors.amberAccent;
    final atr = _averageRange(rows);
    final risk = atr > 0 ? atr * 1.5 : (last * 0.01);
    final stop = last == 0 ? 0.0 : longSignal ? last - risk : shortSignal ? last + risk : 0.0;
    final target = last == 0 ? 0.0 : longSignal ? last + risk * 2 : shortSignal ? last - risk * 2 : 0.0;
    String fmt(double value) => value == 0 ? '—' : value.toStringAsFixed(value >= 100 ? 2 : 4);

    return Container(
      margin: const EdgeInsets.fromLTRB(10, 3, 10, 5),
      padding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
      decoration: BoxDecoration(
        color: _chartPanel,
        border: Border.all(color: _chartCyan.withValues(alpha: .28)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Row(children: [
          const Icon(Icons.candlestick_chart, color: _chartCyan, size: 18),
          const SizedBox(width: 6),
          const Expanded(child: Text('LIVE MARKET · ТОРГОВЫЙ ГРАФИК', maxLines: 1, overflow: TextOverflow.ellipsis,
            style: TextStyle(color: _chartCyan, fontSize: 10, letterSpacing: 1, fontWeight: FontWeight.bold))),
          IconButton(
            visualDensity: VisualDensity.compact, padding: EdgeInsets.zero, constraints: const BoxConstraints(minWidth: 30, minHeight: 30),
            tooltip: 'Обновить свечи', onPressed: _loading ? null : _refresh,
            icon: _loading ? const SizedBox(width: 15, height: 15, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.refresh, size: 18, color: _chartCyan),
          ),
        ]),
        Row(children: [
          Expanded(child: _selector<String>(
            value: _symbol,
            values: const ['BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'XRP-USDT'],
            label: (v) => v,
            changed: (v) { if (v != null) setState(() { _symbol = v; }); _refresh(); },
          )),
          const SizedBox(width: 8),
          Expanded(child: _selector<String>(
            value: _timeframe,
            values: const ['1m', '5m', '15m', '30m', '1H', '4H', '1D'],
            label: (v) => v,
            changed: (v) { if (v != null) setState(() { _timeframe = v; }); _refresh(); },
          )),
        ]),
        const SizedBox(height: 4),
        Row(children: [
          Expanded(child: Text('Цена: ${fmt(last)} USDT', style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.bold))),
          Text(signal, style: TextStyle(color: signalColor, fontSize: 11, fontWeight: FontWeight.w900, letterSpacing: 1)),
          if (rsi != null) Padding(padding: const EdgeInsets.only(left: 8), child: Text('RSI ${rsi.toStringAsFixed(1)}', style: const TextStyle(color: Colors.white60, fontSize: 10))),
        ]),
        if (_error != null) Padding(padding: const EdgeInsets.symmetric(vertical: 5), child: Text('График: $_error', maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(color: Colors.redAccent, fontSize: 10))),
        SizedBox(
          height: 142,
          width: double.infinity,
          child: _candles.isEmpty
              ? Center(child: Text(_loading ? 'Загрузка свечей OKX…' : 'Нет рыночных данных', style: const TextStyle(color: Colors.white54, fontSize: 11)))
              : CustomPaint(painter: _TradingCandlesPainter(rows: rows, signal: longSignal ? 'LONG' : shortSignal ? 'SHORT' : '', entry: last, stop: stop, target: target, sma20: sma20)),
        ),
        const SizedBox(height: 3),
        Wrap(spacing: 10, runSpacing: 3, children: [
          _legend(Colors.greenAccent, 'LONG / вход'),
          _legend(Colors.redAccent, 'SHORT / стоп'),
          _legend(Colors.amberAccent, 'Take-Profit'),
          _legend(_chartCyan, 'SMA20'),
        ]),
        Align(alignment: Alignment.centerLeft, child: Text(
          'Вход ${fmt(last)} · SL ${fmt(stop)} · TP ${fmt(target)} · ${_updated == null ? 'нет обновления' : 'обновлено ${_updated!.hour.toString().padLeft(2, '0')}:${_updated!.minute.toString().padLeft(2, '0')}'}',
          maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: Colors.white70, fontSize: 9),
        )),
        const Align(alignment: Alignment.centerLeft, child: Text(
          'Сигнал расчётный по SMA20/50 и RSI. SL/TP — ориентировочные уровни, не выставленные ордера и не гарантия результата.',
          maxLines: 2, overflow: TextOverflow.ellipsis, style: TextStyle(color: Colors.white38, fontSize: 8),
        )),
      ]),
    );
  }

  Widget _selector<T>({required T value, required List<T> values, required String Function(T) label, required ValueChanged<T?> changed}) =>
    DropdownButtonFormField<T>(
      value: value, isExpanded: true, isDense: true,
      decoration: const InputDecoration(isDense: true, contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 6), border: OutlineInputBorder()),
      style: const TextStyle(fontSize: 11, color: Colors.white),
      items: values.map((v) => DropdownMenuItem<T>(value: v, child: Text(label(v), overflow: TextOverflow.ellipsis))).toList(),
      onChanged: _loading ? null : changed,
    );

  Widget _legend(Color color, String label) => Row(mainAxisSize: MainAxisSize.min, children: [
    Container(width: 7, height: 7, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
    const SizedBox(width: 3), Text(label, style: const TextStyle(color: Colors.white60, fontSize: 8)),
  ]);

  double? _rsi(List<double> closes) {
    if (closes.length < 15) return null;
    var gains = 0.0, losses = 0.0;
    for (var i = closes.length - 14; i < closes.length; i++) {
      final diff = closes[i] - closes[i - 1];
      if (diff > 0) gains += diff; else losses -= diff;
    }
    if (losses == 0) return 100;
    final rs = gains / losses;
    return 100 - 100 / (1 + rs);
  }

  double _averageRange(List<List<dynamic>> rows) {
    if (rows.isEmpty) return 0;
    final sample = rows.length > 14 ? rows.sublist(rows.length - 14) : rows;
    final ranges = sample.map((r) {
      final high = _n(r, 2), low = _n(r, 3);
      return math.max(0.0, high - low);
    }).toList();
    return ranges.isEmpty ? 0 : ranges.reduce((a, b) => a + b) / ranges.length;
  }
}

class _TradingCandlesPainter extends CustomPainter {
  _TradingCandlesPainter({required this.rows, required this.signal, required this.entry, required this.stop, required this.target, required this.sma20});
  final List<List<dynamic>> rows;
  final String signal;
  final double entry, stop, target;
  final double? sma20;

  double _n(List<dynamic> row, int i) => i < row.length ? (double.tryParse(row[i].toString()) ?? 0) : 0;

  @override
  void paint(Canvas canvas, Size size) {
    if (rows.isEmpty || size.width < 30 || size.height < 30) return;
    const left = 5.0, right = 62.0, top = 6.0, bottom = 12.0;
    final plot = Rect.fromLTRB(left, top, math.max(left + 1, size.width - right), size.height - bottom);
    final visible = rows.length > 50 ? rows.sublist(rows.length - 50) : rows;
    var minPrice = double.infinity, maxPrice = 0.0;
    for (final row in visible) { minPrice = math.min(minPrice, _n(row, 3)); maxPrice = math.max(maxPrice, _n(row, 2)); }
    for (final level in [entry, stop, target, if (sma20 != null) sma20!]) {
      if (level > 0) { minPrice = math.min(minPrice, level); maxPrice = math.max(maxPrice, level); }
    }
    if (!minPrice.isFinite || maxPrice <= minPrice) return;
    final pad = (maxPrice - minPrice) * .08;
    minPrice -= pad; maxPrice += pad;
    double y(double price) => plot.bottom - ((price - minPrice) / (maxPrice - minPrice)) * plot.height;

    final gridPaint = Paint()..color = Colors.white.withValues(alpha: .10)..strokeWidth = .5;
    final textStyle = const TextStyle(color: Colors.white54, fontSize: 7);
    for (var i = 0; i <= 3; i++) {
      final yy = plot.top + plot.height * i / 3;
      canvas.drawLine(Offset(plot.left, yy), Offset(plot.right, yy), gridPaint);
      final value = maxPrice - (maxPrice - minPrice) * i / 3;
      _text(canvas, value.toStringAsFixed(value >= 100 ? 1 : 3), Offset(plot.right + 3, yy - 4), textStyle);
    }

    final slot = plot.width / visible.length;
    final bodyWidth = math.max(1.0, slot * .58);
    final wick = Paint()..strokeWidth = 1;
    final upPaint = Paint()..color = Colors.greenAccent;
    final downPaint = Paint()..color = Colors.redAccent;
    final smaPoints = <Offset>[];
    for (var i = 0; i < visible.length; i++) {
      final row = visible[i];
      final open = _n(row, 1), high = _n(row, 2), low = _n(row, 3), close = _n(row, 4);
      final x = plot.left + slot * (i + .5);
      final up = close >= open;
      wick.color = up ? Colors.greenAccent : Colors.redAccent;
      canvas.drawLine(Offset(x, y(high)), Offset(x, y(low)), wick);
      final bodyTop = math.min(y(open), y(close));
      final bodyBottom = math.max(y(open), y(close));
      canvas.drawRect(Rect.fromLTRB(x - bodyWidth / 2, bodyTop, x + bodyWidth / 2, math.max(bodyTop + 1.2, bodyBottom)), up ? upPaint : downPaint);
      if (i >= 19) {
        final start = math.max(0, i - 19);
        final average = visible.skip(start).take(i - start + 1).map((r) => _n(r, 4)).reduce((a, b) => a + b) / (i - start + 1);
        smaPoints.add(Offset(x, y(average)));
      }
    }
    final smaPaint = Paint()..color = _chartCyan..strokeWidth = 1.3..style = PaintingStyle.stroke;
    for (var i = 1; i < smaPoints.length; i++) canvas.drawLine(smaPoints[i - 1], smaPoints[i], smaPaint);

    void level(double value, Color color, String label, {bool dashed = false}) {
      if (value <= 0 || value < minPrice || value > maxPrice) return;
      final yy = y(value);
      final p = Paint()..color = color.withValues(alpha: .9)..strokeWidth = 1;
      if (dashed) {
        for (var x = plot.left; x < plot.right; x += 7) canvas.drawLine(Offset(x, yy), Offset(math.min(x + 3, plot.right), yy), p);
      } else {
        canvas.drawLine(Offset(plot.left, yy), Offset(plot.right, yy), p);
      }
      _text(canvas, label, Offset(plot.right + 3, (yy - 4).clamp(0.0, size.height - 9).toDouble()), TextStyle(color: color, fontSize: 7, fontWeight: FontWeight.bold));
    }
    level(entry, signal == 'LONG' ? Colors.greenAccent : signal == 'SHORT' ? Colors.redAccent : Colors.white70, 'ENTRY');
    level(stop, Colors.redAccent, 'SL', dashed: true);
    level(target, Colors.amberAccent, 'TP', dashed: true);

    if (signal.isNotEmpty) {
      final lastRow = visible.last;
      final xx = plot.left + slot * (visible.length - .5);
      final yy = y(_n(lastRow, 4));
      final color = signal == 'LONG' ? Colors.greenAccent : Colors.redAccent;
      canvas.drawCircle(Offset(xx, yy), 4, Paint()..color = color);
      canvas.drawCircle(Offset(xx, yy), 6, Paint()..color = color.withValues(alpha: .22));
      _text(canvas, signal, Offset(math.max(plot.left, xx - 29), math.max(0.0, yy - 15)), TextStyle(color: color, fontSize: 8, fontWeight: FontWeight.bold));
    }
  }

  void _text(Canvas canvas, String text, Offset offset, TextStyle style) {
    final painter = TextPainter(text: TextSpan(text: text, style: style), textDirection: TextDirection.ltr, maxLines: 1)..layout();
    painter.paint(canvas, offset);
  }

  @override
  bool shouldRepaint(covariant _TradingCandlesPainter oldDelegate) =>
      oldDelegate.rows != rows || oldDelegate.signal != signal || oldDelegate.entry != entry ||
      oldDelegate.stop != stop || oldDelegate.target != target || oldDelegate.sma20 != sma20;
}
