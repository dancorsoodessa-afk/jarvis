import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';

const _osintCyan = Color(0xFF08E6FF);
const _osintBg = Color(0xFF070B12);
const _osintPanel = Color(0xFF0B111B);

/// Public-source OSINT helpers. No scanning, exploitation, or credential collection.
class OsintCenterScreen extends StatefulWidget {
  const OsintCenterScreen({super.key});
  @override
  State<OsintCenterScreen> createState() => _OsintCenterScreenState();
}

class _OsintCenterScreenState extends State<OsintCenterScreen> {
  final _target = TextEditingController();
  bool _busy = false;
  String _result = 'Введите домен, URL или IP-адрес. Инструменты используют только открытые источники.';
  String _kind = 'Домен / URL';

  Future<void> _lookup() async {
    final raw = _target.text.trim();
    if (raw.isEmpty) { setState(() => _result = 'Сначала введите домен, URL или IP.'); return; }
    setState(() { _busy = true; _result = 'Запрашиваю публичные источники…'; });
    final out = <String>[];
    try {
      final uri = Uri.tryParse(raw.contains('://') ? raw : 'https://$raw');
      final host = uri?.host ?? '';
      if (host.isEmpty || host.contains(' ')) throw const FormatException('Не удалось распознать адрес.');
      out.add('ЦЕЛЬ: $host');
      out.add('ТИП: ${InternetAddress.tryParse(host) != null ? "IP-адрес" : "домен"}');

      try {
        final addresses = await InternetAddress.lookup(host).timeout(const Duration(seconds: 8));
        out.add('\nDNS / РАЗРЕШЁННЫЕ АДРЕСА');
        out.addAll(addresses.map((a) => '• ${a.address} (${a.type.name})'));
      } catch (e) { out.add('\nDNS: запрос не выполнен (${_shortError(e)})'); }

      if (InternetAddress.tryParse(host) == null) {
        try {
          final client = HttpClient()..connectionTimeout = const Duration(seconds: 7);
          final req = await client.getUrl(Uri.https('rdap.org', '/domain/$host')).timeout(const Duration(seconds: 8));
          req.headers.set(HttpHeaders.acceptHeader, 'application/rdap+json, application/json');
          final response = await req.close().timeout(const Duration(seconds: 8));
          final body = await response.transform(utf8.decoder).join();
          client.close(force: true);
          out.add('\nRDAP / РЕГИСТРАЦИОННЫЕ ДАННЫЕ (HTTP ${response.statusCode})');
          if (response.statusCode >= 200 && response.statusCode < 300) {
            final data = jsonDecode(body);
            if (data is Map) {
              if (data['ldhName'] != null) out.add('Домен: ${data['ldhName']}');
              if (data['handle'] != null) out.add('Идентификатор: ${data['handle']}');
              final events = data['events'];
              if (events is List) {
                for (final event in events) {
                  if (event is Map && ['registration', 'expiration', 'last changed'].contains(event['eventAction'])) {
                    out.add('${event['eventAction']}: ${event['eventDate'] ?? "нет данных"}');
                  }
                }
              }
              final nameservers = data['nameservers'];
              if (nameservers is List) out.add('NS: ' + nameservers.map((n) => n is Map ? n['ldhName'].toString() : '').where((s) => s.isNotEmpty).take(8).join(', '));
            }
          } else { out.add('RDAP вернул HTTP ${response.statusCode}.'); }
        } catch (e) { out.add('\nRDAP: данные недоступны (${_shortError(e)})'); }
      }

      try {
        final client = HttpClient()..connectionTimeout = const Duration(seconds: 5);
        final request = await client.openUrl('HEAD', Uri.https(host, '/')).timeout(const Duration(seconds: 6));
        request.followRedirects = false;
        final response = await request.close().timeout(const Duration(seconds: 6));
        out.add('\nHTTPS HEAD');
        out.add('HTTP: ${response.statusCode}');
        for (final name in [HttpHeaders.serverHeader, HttpHeaders.contentTypeHeader, HttpHeaders.locationHeader, 'x-powered-by']) {
          final value = response.headers.value(name);
          if (value != null) out.add('$name: $value');
        }
        client.close(force: true);
      } catch (e) { out.add('\nHTTPS HEAD: сайт не ответил на проверку (${_shortError(e)})'); }

      out.add('\nОГРАНИЧЕНИЯ');
      out.add('• Результаты зависят от публичных DNS/RDAP/HTTP-сервисов.');
      out.add('• Это справка, не подтверждение личности владельца и не аудит безопасности.');
      out.add('• Не запускаются сканирование портов, подбор паролей или эксплуатация уязвимостей.');
      if (mounted) setState(() => _result = out.join('\n'));
    } catch (e) {
      if (mounted) setState(() => _result = 'Ошибка: ${_shortError(e)}');
    } finally { if (mounted) setState(() => _busy = false); }
  }

  String _shortError(Object e) => e.toString().replaceFirst('Exception: ', '').split('\n').first;

  @override
  void dispose() { _target.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: _osintBg,
    appBar: AppBar(title: const Text('OSINT / Разведка'), backgroundColor: _osintBg, foregroundColor: _osintCyan),
    body: ListView(padding: const EdgeInsets.all(16), children: [
      const Text('ПУБЛИЧНЫЕ ИСТОЧНИКИ', style: TextStyle(color: _osintCyan, fontWeight: FontWeight.bold, letterSpacing: 1.3)),
      const SizedBox(height: 8),
      const Text('Проверка домена или IP по открытым данным. Используйте только законные цели и публичную информацию.', style: TextStyle(color: Colors.white70)),
      const SizedBox(height: 16),
      TextField(controller: _target, style: const TextStyle(color: Colors.white), keyboardType: TextInputType.url, decoration: InputDecoration(labelText: 'Домен, URL или IP', hintText: 'example.com', labelStyle: const TextStyle(color: _osintCyan), enabledBorder: OutlineInputBorder(borderSide: BorderSide(color: _osintCyan.withValues(alpha: .4))), focusedBorder: const OutlineInputBorder(borderSide: BorderSide(color: _osintCyan)))),
      const SizedBox(height: 12),
      FilledButton.icon(onPressed: _busy ? null : _lookup, icon: _busy ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.travel_explore), label: Text(_busy ? 'Проверка…' : 'Собрать открытые данные')),
      const SizedBox(height: 16),
      Container(padding: const EdgeInsets.all(14), decoration: BoxDecoration(color: _osintPanel, border: Border.all(color: _osintCyan.withValues(alpha: .25)), borderRadius: BorderRadius.circular(12)), child: SelectableText(_result, style: const TextStyle(color: Colors.white70, height: 1.5, fontFamily: 'monospace'))),
      const SizedBox(height: 16),
      const Text('Следующие инструменты можно подключить отдельно: поиск по новостям и публичным профилям, проверка утечек через легальные сервисы, экспорт отчёта. Скрытые аккаунты и закрытые данные не извлекаются.', style: TextStyle(color: Colors.white54)),
    ]),
  );
}
