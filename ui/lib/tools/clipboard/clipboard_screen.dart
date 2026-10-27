import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class JarvisClipboardScreen extends StatefulWidget {
  const JarvisClipboardScreen({super.key});
  @override
  State<JarvisClipboardScreen> createState() => _JarvisClipboardScreenState();
}
class _JarvisClipboardScreenState extends State<JarvisClipboardScreen> {
  final _text = TextEditingController();
  String _status = 'Буфер обмена ещё не прочитан.';
  Future<void> _read() async {
    try {
      final data = await Clipboard.getData(Clipboard.kTextPlain);
      if (!mounted) return;
      setState(() { _text.text = data?.text ?? ''; _status = data?.text == null ? 'В буфере нет текста.' : 'Текст прочитан из буфера.'; });
    } catch (e) { if (mounted) setState(() => _status = 'Не удалось прочитать буфер: $e'); }
  }
  Future<void> _write() async {
    try { await Clipboard.setData(ClipboardData(text: _text.text)); if (mounted) setState(() => _status = 'Текст записан в буфер обмена.'); }
    catch (e) { if (mounted) setState(() => _status = 'Не удалось записать буфер: $e'); }
  }
  @override
  void dispose() { _text.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Буфер обмена')),
    body: ListView(padding: const EdgeInsets.all(16), children: [
      TextField(controller: _text, minLines: 4, maxLines: 10, decoration: const InputDecoration(labelText: 'Текст', border: OutlineInputBorder())),
      const SizedBox(height: 12),
      Wrap(spacing: 8, children: [
        FilledButton.icon(onPressed: _read, icon: const Icon(Icons.content_paste), label: const Text('Прочитать')),
        OutlinedButton.icon(onPressed: _write, icon: const Icon(Icons.copy), label: const Text('Записать')),
      ]),
      const SizedBox(height: 12), Text(_status),
    ]),
  );
}
