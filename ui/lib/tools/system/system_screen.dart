import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class JarvisSystemScreen extends StatefulWidget {
  const JarvisSystemScreen({super.key});
  @override
  State<JarvisSystemScreen> createState() => _JarvisSystemScreenState();
}
class _JarvisSystemScreenState extends State<JarvisSystemScreen> {
  static const _channel = MethodChannel('com.dancorsoodessa.jarvis/device');
  Map<String, dynamic> _info = const {};
  String _status = 'Загрузка системной информации…';
  bool _busy = false;
  @override
  void initState() { super.initState(); _refresh(); }
  Future<void> _refresh() async {
    setState(() { _busy = true; _status = 'Читаю состояние Android…'; });
    try {
      final info = await _channel.invokeMapMethod<String, dynamic>('systemInfo');
      if (!mounted) return;
      setState(() { _info = info ?? const {}; _status = 'Системная информация обновлена'; });
    } catch (e) {
      if (mounted) setState(() => _status = 'Нативная диагностика недоступна: $e');
    } finally { if (mounted) setState(() => _busy = false); }
  }
  String _mb(dynamic value) => value is num ? '${(value / (1024 * 1024)).toStringAsFixed(0)} МБ' : '—';
  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    return Scaffold(
      appBar: AppBar(title: const Text('Система и диагностика'), actions: [IconButton(onPressed: _busy ? null : _refresh, icon: const Icon(Icons.refresh))]),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        const Text('ДИАГНОСТИКА ANDROID', style: TextStyle(color: Color(0xFF37D5EE), letterSpacing: 1.5, fontWeight: FontWeight.bold)),
        const SizedBox(height: 12),
        _row('Версия Android', '${_info['androidVersion'] ?? '—'}'),
        _row('API level', '${_info['sdkInt'] ?? '—'}'),
        _row('PID JARVIS', '${_info['processId'] ?? '—'}'),
        _row('ОЗУ всего', _mb(_info['totalMemoryBytes'])),
        _row('ОЗУ свободно', _mb(_info['availableMemoryBytes'])),
        _row('Лимит heap приложения', _mb(_info['appMaxHeapBytes'])),
        _row('Состояние памяти', _info['lowMemory'] == true ? 'Android сообщает о нехватке памяти' : 'Норма / нет сигнала low-memory'),
        _row('Время устройства', '${now.toLocal()}'),
        const SizedBox(height: 8),
        Text(_status),
        const SizedBox(height: 8),
        const Text('Android ограничивает доступ к процессам других приложений. JARVIS не завершает чужие процессы и не обходит системные ограничения.', style: TextStyle(color: Colors.white60, fontSize: 12)),
      ]),
    );
  }
  Widget _row(String label, String value) => Card(child: ListTile(title: Text(label), subtitle: SelectableText(value)));
}
