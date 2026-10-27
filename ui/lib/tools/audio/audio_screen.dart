import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class JarvisAudioScreen extends StatefulWidget {
  const JarvisAudioScreen({super.key});
  @override
  State<JarvisAudioScreen> createState() => _JarvisAudioScreenState();
}
class _JarvisAudioScreenState extends State<JarvisAudioScreen> {
  static const _channel = MethodChannel('com.dancorsoodessa.jarvis/device');
  double _volume = 50;
  bool _busy = false;
  String _status = 'Громкость мультимедиа Android.';
  Future<void> _read() async {
    try {
      final value = await _channel.invokeMapMethod<String, dynamic>('getVolume');
      if (!mounted || value == null) return;
      setState(() { _volume = (value['percent'] as num?)?.toDouble() ?? 50; _status = 'Текущая громкость: ${_volume.round()}%'; });
    } catch (e) { if (mounted) setState(() => _status = 'Ошибка чтения громкости: $e'); }
  }
  Future<void> _apply() async {
    setState(() => _busy = true);
    try {
      await _channel.invokeMethod<bool>('setVolume', {'percent': _volume.round()});
      if (mounted) setState(() => _status = 'Громкость установлена: ${_volume.round()}%');
    } catch (e) { if (mounted) setState(() => _status = 'Ошибка изменения громкости: $e'); }
    finally { if (mounted) setState(() => _busy = false); }
  }
  @override
  void initState() { super.initState(); _read(); }
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Громкость')),
    body: ListView(padding: const EdgeInsets.all(16), children: [
      Text('Громкость мультимедиа: ${_volume.round()}%'),
      Slider(value: _volume, min: 0, max: 100, divisions: 100, label: '${_volume.round()}%', onChanged: _busy ? null : (value) => setState(() => _volume = value)),
      FilledButton.icon(onPressed: _busy ? null : _apply, icon: const Icon(Icons.volume_up), label: const Text('Применить')),
      OutlinedButton.icon(onPressed: _busy ? null : _read, icon: const Icon(Icons.refresh), label: const Text('Прочитать текущую')),
      const SizedBox(height: 8), Text(_status),
    ]),
  );
}
