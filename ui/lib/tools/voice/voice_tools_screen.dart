import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';

class JarvisVoiceToolsScreen extends StatefulWidget {
  const JarvisVoiceToolsScreen({super.key});
  @override
  State<JarvisVoiceToolsScreen> createState() => _JarvisVoiceToolsScreenState();
}
class _JarvisVoiceToolsScreenState extends State<JarvisVoiceToolsScreen> {
  final _text = TextEditingController(text: 'Система JARVIS готова.');
  final _tts = FlutterTts();
  double _rate = 0.45;
  double _pitch = 0.9;
  bool _busy = false;
  String _status = 'Синтез речи запускается только после нажатия кнопки.';
  Future<void> _speak() async {
    if (_text.text.trim().isEmpty) { setState(() => _status = 'Введите текст для озвучивания.'); return; }
    setState(() { _busy = true; _status = 'Подготавливаю голос…'; });
    try {
      await _tts.setLanguage('ru-RU');
      await _tts.setSpeechRate(_rate);
      await _tts.setPitch(_pitch);
      await _tts.setVolume(1.0);
      await _tts.speak(_text.text.trim());
      if (mounted) setState(() => _status = 'Передано системному синтезатору речи Android.');
    } catch (e) {
      if (mounted) setState(() => _status = 'Ошибка синтеза речи: $e');
    } finally { if (mounted) setState(() => _busy = false); }
  }
  Future<void> _stop() async {
    try { await _tts.stop(); if (mounted) setState(() => _status = 'Озвучивание остановлено.'); }
    catch (e) { if (mounted) setState(() => _status = 'Не удалось остановить голос: $e'); }
  }
  Future<void> _stopOnDispose() async { try { await _tts.stop(); } catch (_) {} }
  @override
  void dispose() { unawaited(_stopOnDispose()); _text.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Голос JARVIS')),
    body: ListView(padding: const EdgeInsets.all(16), children: [
      TextField(controller: _text, minLines: 3, maxLines: 8, decoration: const InputDecoration(labelText: 'Текст для озвучивания', border: OutlineInputBorder())),
      const SizedBox(height: 16),
      Text('Скорость: ${_rate.toStringAsFixed(2)}'),
      Slider(value: _rate, min: 0.2, max: 0.8, divisions: 12, onChanged: (v) => setState(() => _rate = v)),
      Text('Высота голоса: ${_pitch.toStringAsFixed(2)}'),
      Slider(value: _pitch, min: 0.5, max: 1.5, divisions: 20, onChanged: (v) => setState(() => _pitch = v)),
      Wrap(spacing: 8, children: [
        FilledButton.icon(onPressed: _busy ? null : _speak, icon: const Icon(Icons.volume_up), label: const Text('Озвучить')),
        OutlinedButton.icon(onPressed: _stop, icon: const Icon(Icons.stop), label: const Text('Стоп')),
      ]),
      const SizedBox(height: 12), Text(_status),
      const Text('Используется голосовой движок, установленный в Android. Доступность мужского голоса зависит от выбранного системного движка и установленных голосов.', style: TextStyle(color: Colors.white60, fontSize: 12)),
    ]),
  );
}
