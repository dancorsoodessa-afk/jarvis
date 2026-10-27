import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class JarvisMemoryScreen extends StatefulWidget {
  const JarvisMemoryScreen({super.key});
  @override
  State<JarvisMemoryScreen> createState() => _JarvisMemoryScreenState();
}
class _JarvisMemoryScreenState extends State<JarvisMemoryScreen> {
  static const _notesKey = 'jarvis_android_notes_v1';
  static const _timerKey = 'jarvis_android_timer_due_v1';
  static const _graphKey = 'jarvis_android_graph_v1';
  final _note = TextEditingController();
  final _minutes = TextEditingController(text: '5');
  final _subject = TextEditingController();
  final _relation = TextEditingController(text: 'связан с');
  final _object = TextEditingController();
  List<String> _notes = [];
  List<String> _graph = [];
  String _status = 'Загрузка памяти…';
  DateTime? _due;
  Timer? _timer;
  @override
  void initState() { super.initState(); _load(); }
  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final notes = prefs.getStringList(_notesKey) ?? <String>[];
    final dueMs = prefs.getInt(_timerKey);
    final graph = prefs.getStringList(_graphKey) ?? <String>[];
    if (!mounted) return;
    setState(() { _notes = notes; _graph = graph; _due = dueMs == null ? null : DateTime.fromMillisecondsSinceEpoch(dueMs); _status = 'Локальная память устройства'; });
    _armTimer();
  }
  Future<void> _saveNotes() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_notesKey, _notes);
  }
  Future<void> _addNote() async {
    final value = _note.text.trim();
    if (value.isEmpty) return;
    setState(() { _notes = [..._notes, value].take(500).toList(); _note.clear(); _status = 'Заметка сохранена на устройстве'; });
    await _saveNotes();
  }
  Future<void> _removeNote(int index) async {
    setState(() { _notes.removeAt(index); _status = 'Заметка удалена'; });
    await _saveNotes();
  }
  Future<void> _addRelation() async {
    final subject = _subject.text.trim();
    final relation = _relation.text.trim();
    final object = _object.text.trim();
    if (subject.isEmpty || relation.isEmpty || object.isEmpty) {
      setState(() => _status = 'Заполните сущность, связь и объект.');
      return;
    }
    setState(() {
      _graph = [..._graph, '$subject — $relation → $object'].take(500).toList();
      _subject.clear();
      _object.clear();
      _status = 'Связь добавлена в локальный граф знаний.';
    });
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_graphKey, _graph);
  }
  Future<void> _removeRelation(int index) async {
    setState(() { _graph.removeAt(index); _status = 'Связь удалена из графа знаний.'; });
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_graphKey, _graph);
  }
  Future<void> _startTimer() async {
    final mins = int.tryParse(_minutes.text.trim());
    if (mins == null || mins < 1 || mins > 1440) { setState(() => _status = 'Введите от 1 до 1440 минут'); return; }
    _due = DateTime.now().add(Duration(minutes: mins));
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_timerKey, _due!.millisecondsSinceEpoch);
    _armTimer();
    if (mounted) setState(() => _status = 'Таймер установлен на $mins мин. Оставьте приложение запущенным для сигнала.');
  }
  void _armTimer() {
    _timer?.cancel();
    final due = _due;
    if (due == null) return;
    final remaining = due.difference(DateTime.now());
    if (remaining <= Duration.zero) {
      _timer = Timer(Duration.zero, _finishTimer);
    } else {
      _timer = Timer(remaining, _finishTimer);
    }
  }
  Future<void> _finishTimer() async {
    _due = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_timerKey);
    if (!mounted) return;
    setState(() => _status = 'Время таймера истекло');
    await showDialog<void>(context: context, builder: (ctx) => AlertDialog(
      title: const Text('JARVIS — таймер'),
      content: const Text('Время вышло.'),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Закрыть'))],
    ));
  }
  @override
  void dispose() { _timer?.cancel(); _note.dispose(); _minutes.dispose(); _subject.dispose(); _relation.dispose(); _object.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Заметки, напоминания и таймер')),
    body: ListView(padding: const EdgeInsets.all(16), children: [
      const Text('Сохранённые заметки', style: TextStyle(color: Color(0xFF37D5EE), fontWeight: FontWeight.bold, letterSpacing: 1.4)),
      const SizedBox(height: 8),
      TextField(controller: _note, minLines: 2, maxLines: 4, decoration: const InputDecoration(labelText: 'Новая заметка', border: OutlineInputBorder())),
      const SizedBox(height: 8),
      FilledButton.icon(onPressed: _addNote, icon: const Icon(Icons.save), label: const Text('Сохранить заметку')),
      ..._notes.asMap().entries.map((entry) => Card(child: ListTile(
        title: Text(entry.value),
        trailing: IconButton(icon: const Icon(Icons.delete_outline), onPressed: () => _removeNote(entry.key)),
      ))),
      const Divider(height: 28),
      const Text('Связи между данными', style: TextStyle(color: Color(0xFF37D5EE), fontWeight: FontWeight.bold, letterSpacing: 1.4)),
      const SizedBox(height: 8),
      TextField(controller: _subject, decoration: const InputDecoration(labelText: 'Сущность / субъект', border: OutlineInputBorder())),
      const SizedBox(height: 8),
      TextField(controller: _relation, decoration: const InputDecoration(labelText: 'Связь', border: OutlineInputBorder())),
      const SizedBox(height: 8),
      TextField(controller: _object, decoration: const InputDecoration(labelText: 'Объект / значение', border: OutlineInputBorder())),
      const SizedBox(height: 8),
      FilledButton.icon(onPressed: _addRelation, icon: const Icon(Icons.hub), label: const Text('Добавить связь')),
      ..._graph.asMap().entries.map((entry) => Card(child: ListTile(
        title: Text(entry.value),
        trailing: IconButton(icon: const Icon(Icons.delete_outline), onPressed: () => _removeRelation(entry.key)),
      ))),
      const Divider(height: 28),
      const Text('Таймер', style: TextStyle(color: Color(0xFF37D5EE), fontWeight: FontWeight.bold, letterSpacing: 1.4)),
      TextField(controller: _minutes, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Минуты (1–1440)', border: OutlineInputBorder())),
      const SizedBox(height: 8),
      FilledButton.icon(onPressed: _startTimer, icon: const Icon(Icons.timer), label: const Text('Установить таймер')),
      if (_due != null) Text('Окончание: ${_due!.toLocal()}'),
      const SizedBox(height: 12),
      Text(_status, style: const TextStyle(color: Colors.white70)),
      const Text('Заметки хранятся локально. Этот таймер показывает диалог, пока приложение активно; системное уведомление в фоне не гарантируется.', style: TextStyle(color: Colors.white54, fontSize: 12)),
    ]),
  );
}
