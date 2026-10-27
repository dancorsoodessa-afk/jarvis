import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class JarvisScreenshotScreen extends StatefulWidget {
  const JarvisScreenshotScreen({super.key});
  @override
  State<JarvisScreenshotScreen> createState() => _JarvisScreenshotScreenState();
}
class _JarvisScreenshotScreenState extends State<JarvisScreenshotScreen> {
  static const _channel = MethodChannel('com.dancorsoodessa.jarvis/device');
  bool _busy = false;
  String _status = 'Снимок будет сохранён в галерею: Pictures/JARVIS.';
  String? _uri;
  Future<void> _capture() async {
    setState(() { _busy = true; _status = 'Делаю снимок экрана…'; _uri = null; });
    try {
      final uri = await _channel.invokeMethod<String>('captureScreenshot');
      if (mounted) setState(() { _uri = uri; _status = uri == null ? 'Android не вернул URI изображения.' : 'Снимок сохранён в Pictures/JARVIS.'; });
    } catch (e) {
      if (mounted) setState(() => _status = 'Не удалось сделать снимок: $e');
    } finally { if (mounted) setState(() => _busy = false); }
  }
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Снимок экрана')),
    body: ListView(padding: const EdgeInsets.all(16), children: [
      const Icon(Icons.screenshot_monitor, size: 64, color: Color(0xFF37D5EE)),
      const SizedBox(height: 12),
      const Text('Снимок окна JARVIS', textAlign: TextAlign.center, style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
      const SizedBox(height: 12),
      FilledButton.icon(onPressed: _busy ? null : _capture, icon: const Icon(Icons.camera_alt), label: Text(_busy ? 'Снимок…' : 'Сделать снимок')),
      const SizedBox(height: 12),
      Text(_status),
      if (_uri != null) SelectableText(_uri!, style: const TextStyle(fontSize: 12, color: Colors.white60)),
      const SizedBox(height: 8),
      const Text('Android 10 и новее сохраняет PNG в галерею в папку Pictures/JARVIS. Это снимок окна приложения, а не скрытая запись экрана.', style: TextStyle(color: Colors.white60, fontSize: 12)),
    ]),
  );
}
