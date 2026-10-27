import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class JarvisAppsScreen extends StatefulWidget {
  const JarvisAppsScreen({super.key});
  @override
  State<JarvisAppsScreen> createState() => _JarvisAppsScreenState();
}
class _JarvisAppsScreenState extends State<JarvisAppsScreen> {
  static const _channel = MethodChannel('com.dancorsoodessa.jarvis/device');
  List<Map<String, String>> _apps = [];
  bool _busy = false;
  String _status = 'Нажмите «Обновить список».';
  Future<void> _load() async {
    setState(() { _busy = true; _status = 'Получаю список приложений…'; });
    try {
      final raw = await _channel.invokeListMethod<dynamic>('listLaunchableApps');
      final apps = (raw ?? const <dynamic>[]).whereType<Map>().map((entry) => {
        'label': entry['label']?.toString() ?? 'Без названия',
        'packageName': entry['packageName']?.toString() ?? '',
      }).where((entry) => entry['packageName']!.isNotEmpty).toList();
      if (mounted) setState(() { _apps = apps; _status = 'Найдено приложений: ${apps.length}'; });
    } catch (e) {
      if (mounted) setState(() => _status = 'Нативный модуль недоступен: $e');
    } finally { if (mounted) setState(() => _busy = false); }
  }
  Future<void> _launch(String packageName) async {
    try { await _channel.invokeMethod<bool>('launchApp', {'packageName': packageName}); }
    catch (e) { if (mounted) setState(() => _status = 'Не удалось запустить приложение: $e'); }
  }
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Приложения Android'), actions: [IconButton(onPressed: _busy ? null : _load, icon: const Icon(Icons.refresh))]),
    body: ListView(padding: const EdgeInsets.all(12), children: [
      Text(_status),
      const SizedBox(height: 8),
      FilledButton.icon(onPressed: _busy ? null : _load, icon: const Icon(Icons.apps), label: const Text('Обновить список')),
      ..._apps.map((app) => Card(child: ListTile(
        leading: const Icon(Icons.android),
        title: Text(app['label']!),
        subtitle: Text(app['packageName']!, style: const TextStyle(fontSize: 11)),
        trailing: IconButton(tooltip: 'Запустить', icon: const Icon(Icons.play_arrow), onPressed: () => _launch(app['packageName']!)),
      ))),
      const SizedBox(height: 8),
      const Text('Показываются приложения с доступной точкой запуска, которые Android разрешил обнаружить.', style: TextStyle(color: Colors.white60, fontSize: 12)),
    ]),
  );
}
