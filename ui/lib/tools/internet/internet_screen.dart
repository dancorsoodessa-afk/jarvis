import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class JarvisInternetScreen extends StatefulWidget {
  const JarvisInternetScreen({super.key});
  @override
  State<JarvisInternetScreen> createState() => _JarvisInternetScreenState();
}
class _JarvisInternetScreenState extends State<JarvisInternetScreen> {
  static const _channel = MethodChannel('com.dancorsoodessa.jarvis/device');
  final _query = TextEditingController();
  bool _busy = false;
  String _result = 'Введите запрос для поиска или город для погоды.';
  Future<String> _get(Uri uri) async {
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 10);
    try {
      final request = await client.getUrl(uri).timeout(const Duration(seconds: 10));
      request.headers.set(HttpHeaders.userAgentHeader, 'JARVIS-Android/1.0');
      request.headers.set(HttpHeaders.acceptHeader, 'application/json,text/html');
      final response = await request.close().timeout(const Duration(seconds: 12));
      final body = await response.transform(utf8.decoder).join().timeout(const Duration(seconds: 12));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw HttpException('HTTP ${response.statusCode}', uri: uri);
      }
      return body;
    } finally { client.close(force: true); }
  }
  Future<void> _run(bool weather) async {
    final value = _query.text.trim();
    if (value.isEmpty) { setState(() => _result = 'Сначала введите запрос или город.'); return; }
    setState(() { _busy = true; _result = 'Запрос выполняется…'; });
    try {
      final result = weather ? await _weather(value) : await _search(value);
      if (mounted) setState(() => _result = result);
    } catch (e) {
      if (mounted) setState(() => _result = 'Ошибка запроса: $e');
    } finally { if (mounted) setState(() => _busy = false); }
  }
  Future<void> _openUrl() async {
    final value = _query.text.trim();
    try {
      await _channel.invokeMethod<bool>('openUrl', {'url': value});
      if (mounted) setState(() => _result = 'Передано Android для открытия URL: $value');
    } catch (e) {
      if (mounted) setState(() => _result = 'Не удалось открыть URL: $e');
    }
  }
  Future<String> _search(String query) async {
    final html = await _get(Uri.https('html.duckduckgo.com', '/html/', {'q': query}));
    final links = <String>[];
    final pattern = RegExp(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', caseSensitive: false, dotAll: true);
    for (final match in pattern.allMatches(html).take(8)) {
      final url = _decode(match.group(1) ?? '');
      final title = _decode((match.group(2) ?? '').replaceAll(RegExp(r'<[^>]+>'), '').replaceAll(RegExp(r'\s+'), ' '));
      if (url.isNotEmpty && title.isNotEmpty) links.add('$title\n$url');
    }
    if (links.isEmpty) return 'Поиск завершён, но HTML-результаты не распознаны. Попробуйте другой запрос или откройте поисковик в браузере.';
    return 'Результаты поиска: $query\n\n${links.join('\n\n')}';
  }
  String _decode(String value) => value
    .replaceAll('&amp;', '&').replaceAll('&quot;', '"').replaceAll('&#x27;', "'")
    .replaceAll('&lt;', '<').replaceAll('&gt;', '>');
  Future<String> _weather(String city) async {
    final geoText = await _get(Uri.https('geocoding-api.open-meteo.com', '/v1/search', {'name': city, 'count': '1', 'language': 'ru', 'format': 'json'}));
    final geo = jsonDecode(geoText);
    final results = geo is Map ? geo['results'] : null;
    if (results is! List || results.isEmpty || results.first is! Map) return 'Город не найден: $city';
    final place = Map<String, dynamic>.from(results.first as Map);
    final lat = place['latitude'];
    final lon = place['longitude'];
    if (lat is! num || lon is! num) return 'Сервис геокодирования не вернул координаты.';
    final forecastText = await _get(Uri.https('api.open-meteo.com', '/v1/forecast', {
      'latitude': lat.toString(), 'longitude': lon.toString(),
      'current': 'temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,wind_speed_10m,weather_code',
      'daily': 'temperature_2m_max,temperature_2m_min,precipitation_probability_max',
      'forecast_days': '3', 'timezone': 'auto'
    }));
    final forecast = jsonDecode(forecastText);
    if (forecast is! Map) return 'Неожиданный ответ погодного сервиса.';
    final current = forecast['current'] is Map ? Map<String, dynamic>.from(forecast['current'] as Map) : <String, dynamic>{};
    final daily = forecast['daily'] is Map ? Map<String, dynamic>.from(forecast['daily'] as Map) : <String, dynamic>{};
    final times = daily['time'] is List ? daily['time'] as List : const [];
    final highs = daily['temperature_2m_max'] is List ? daily['temperature_2m_max'] as List : const [];
    final lows = daily['temperature_2m_min'] is List ? daily['temperature_2m_min'] as List : const [];
    final rain = daily['precipitation_probability_max'] is List ? daily['precipitation_probability_max'] as List : const [];
    final lines = <String>[
      'Погода: ${place['name'] ?? city}, ${place['country'] ?? ''}',
      'Сейчас: ${current['temperature_2m'] ?? '—'} °C; ощущается ${current['apparent_temperature'] ?? '—'} °C',
      'Ветер: ${current['wind_speed_10m'] ?? '—'} км/ч; влажность: ${current['relative_humidity_2m'] ?? '—'}%',
      'Осадки сейчас: ${current['precipitation'] ?? '—'} мм',
      'Прогноз на 3 дня:'
    ];
    for (var i = 0; i < times.length && i < 3; i++) {
      lines.add('${times[i]}: ${lows.length > i ? lows[i] : '—'}…${highs.length > i ? highs[i] : '—'} °C; вероятность осадков ${rain.length > i ? rain[i] : '—'}%');
    }
    lines.add('Источник: Open-Meteo');
    return lines.join('\n');
  }
  @override
  void dispose() { _query.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Интернет и погода')),
    body: ListView(padding: const EdgeInsets.all(16), children: [
      TextField(controller: _query, decoration: const InputDecoration(labelText: 'Поисковый запрос или город', border: OutlineInputBorder()), onSubmitted: (_) => _run(false)),
      const SizedBox(height: 12),
      Wrap(spacing: 8, runSpacing: 8, children: [
        FilledButton.icon(onPressed: _busy ? null : () => _run(false), icon: const Icon(Icons.search), label: const Text('Поиск в интернете')),
        OutlinedButton.icon(onPressed: _busy ? null : () => _run(true), icon: const Icon(Icons.cloud), label: const Text('Погода на 3 дня')),
        OutlinedButton.icon(onPressed: _busy ? null : _openUrl, icon: const Icon(Icons.open_in_browser), label: const Text('Открыть URL')),
      ]),
      const SizedBox(height: 16),
      SelectableText(_result, style: const TextStyle(height: 1.45)),
    ]),
  );
}
