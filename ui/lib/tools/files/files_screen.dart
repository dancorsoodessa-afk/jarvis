import 'dart:convert';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

class JarvisFilesScreen extends StatefulWidget {
  const JarvisFilesScreen({super.key});
  @override
  State<JarvisFilesScreen> createState() => _JarvisFilesScreenState();
}
class _JarvisFilesScreenState extends State<JarvisFilesScreen> {
  bool _busy = false;
  String _status = 'Выберите файлы через системный диалог Android.';
  List<PlatformFile> _files = [];
  String _preview = '';
  Future<void> _pick() async {
    setState(() { _busy = true; _status = 'Открываю системный выбор файлов…'; _preview = ''; });
    try {
      final files = await FilePicker.pickFiles();
      if (!mounted) return;
      if (files.isEmpty) {
        setState(() => _status = 'Выбор отменён.');
        return;
      }
      setState(() { _files = files; _status = 'Выбрано файлов: ${files.length}'; });
    } catch (e) {
      if (mounted) setState(() => _status = 'Не удалось открыть файлы: $e');
    } finally { if (mounted) setState(() => _busy = false); }
  }
  Future<void> _showText(PlatformFile file) async {
    try {
      final ext = (file.extension ?? '').toLowerCase();
      if (!const {'txt','md','json','csv','log','xml','yaml','yml'}.contains(ext)) {
        setState(() => _preview = 'Предпросмотр текста доступен для TXT, MD, JSON, CSV, LOG и YAML.');
        return;
      }
      final bytes = await file.readAsBytes();
      if (bytes.length > 1024 * 1024) {
        setState(() => _preview = 'Файл больше 1 МБ; текстовый предпросмотр ограничен.');
        return;
      }
      if (mounted) setState(() => _preview = utf8.decode(bytes, allowMalformed: true));
    } catch (e) {
      if (mounted) setState(() => _preview = 'Не удалось прочитать файл: $e');
    }
  }
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Файлы')),
    body: ListView(padding: const EdgeInsets.all(16), children: [
      const Text('РАБОТА С ФАЙЛАМИ ANDROID', style: TextStyle(color: Color(0xFF37D5EE), fontWeight: FontWeight.bold, letterSpacing: 1.2)),
      const SizedBox(height: 8),
      FilledButton.icon(onPressed: _busy ? null : _pick, icon: const Icon(Icons.folder_open), label: Text(_busy ? 'Открытие…' : 'Выбрать файлы')),
      const SizedBox(height: 8), Text(_status),
      ..._files.map((file) => Card(child: ListTile(
        leading: const Icon(Icons.insert_drive_file),
        title: Text(file.name, maxLines: 2, overflow: TextOverflow.ellipsis),
        subtitle: Text(file.extension ?? 'без расширения'),
        trailing: IconButton(icon: const Icon(Icons.visibility), onPressed: () => _showText(file)),
      ))),
      if (_preview.isNotEmpty) ...[
        const SizedBox(height: 12),
        const Text('ПРЕДПРОСМОТР', style: TextStyle(color: Color(0xFF37D5EE), fontWeight: FontWeight.bold)),
        const SizedBox(height: 6),
        SelectableText(_preview),
      ],
      const SizedBox(height: 12),
      const Text('Доступ предоставляется только к файлам, которые вы выбрали в системном диалоге. Удаление и произвольный доступ к файловой системе не выполняются.', style: TextStyle(color: Colors.white60, fontSize: 12)),
    ]),
  );
}
