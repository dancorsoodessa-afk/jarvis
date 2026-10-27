import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class JarvisPromptLibraryScreen extends StatefulWidget {
  const JarvisPromptLibraryScreen({super.key});
  @override
  State<JarvisPromptLibraryScreen> createState() => _JarvisPromptLibraryScreenState();
}

class _JarvisPromptLibraryScreenState extends State<JarvisPromptLibraryScreen> {
  static const _key = 'jarvis_prompt_library_v1';
  final _search = TextEditingController();
  List<Map<String, String>> _items = [];
  bool _ready = false;
  static const _defaults = <Map<String, String>>[
    {'title':'Анализ документа','category':'Документы','prompt':'Проанализируй прикреплённые документы: краткое содержание, ключевые факты, даты, цифры, риски и противоречия. Не выдумывай отсутствующие сведения.'},
    {'title':'Краткое резюме','category':'Документы','prompt':'Сделай структурированное резюме прикреплённого документа: цель, основные тезисы, выводы и важные детали.'},
    {'title':'Извлечь данные','category':'Документы','prompt':'Извлеки из документов имена, даты, суммы, адреса, номера и обязательства. Сохрани точность и отметь неоднозначности.'},
    {'title':'Сравнить документы','category':'Документы','prompt':'Сравни прикреплённые документы: совпадения, различия, изменения, пропущенные пункты и противоречия.'},
    {'title':'Перевод документа','category':'Документы','prompt':'Переведи прикреплённый документ на русский язык, сохранив смысл, структуру, числа и названия.'},
    {'title':'Проверить ошибки','category':'Документы','prompt':'Проверь документ на ошибки, противоречия, неточности и недостающие сведения. Предложи исправления, не меняя факты.'},
    {'title':'Крипторынок','category':'Криптовалюта','prompt':'Проанализируй актуальные данные указанной криптовалюты. Раздели факты и сценарии. Укажи таймфрейм, условия LONG/SHORT/WAIT, вход, Stop-Loss, Take-Profit и риск. Не обещай гарантированную прибыль.'},
    {'title':'Технический анализ','category':'Криптовалюта','prompt':'Проведи технический анализ по актуальным данным: тренд, уровни, свечи, SMA20/SMA50, RSI, сценарии вверх/вниз и условия отмены. Если данных нет — сообщи.'},
    {'title':'План действий','category':'Работа','prompt':'Разбей задачу на шаги. Для каждого укажи результат, проверку и риски. Не утверждай, что действие выполнено без проверки.'},
    {'title':'Исправить ошибку','category':'Разработка','prompt':'Найди первопричину ошибки, предложи минимальное исправление и запусти проверки. Не заявляй об успехе без результата проверки.'},
    {'title':'Поиск информации','category':'Интернет','prompt':'Ответь по существу, отдели факты от предположений, используй актуальные надёжные источники и укажи ссылки. Не придумывай источники.'},
    {'title':'Улучшить текст','category':'Тексты','prompt':'Исправь грамматику, ясность и структуру текста, сохранив исходный смысл и факты. Выведи готовый вариант.'},
  ];
  @override
  void initState() { super.initState(); _load(); }
  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    var items = <Map<String, String>>[];
    final raw = prefs.getString(_key);
    if (raw != null) { try { items = (jsonDecode(raw) as List).map((e) => Map<String, String>.from(e as Map)).toList(); } catch (_) {} }
    if (items.isEmpty) items = _defaults.map((e) => Map<String, String>.from(e)).toList();
    if (!mounted) return;
    setState(() { _items = items; _ready = true; });
    await _save();
  }
  Future<void> _save() async => (await SharedPreferences.getInstance()).setString(_key, jsonEncode(_items));
  List<Map<String, String>> get _visible {
    final q = _search.text.trim().toLowerCase();
    return q.isEmpty ? _items : _items.where((p) => '${p['title']} ${p['category']} ${p['prompt']}'.toLowerCase().contains(q)).toList();
  }
  Future<void> _edit([Map<String, String>? old]) async {
    final title = TextEditingController(text: old?['title'] ?? '');
    final category = TextEditingController(text: old?['category'] ?? 'Мои промпты');
    final prompt = TextEditingController(text: old?['prompt'] ?? '');
    final value = await showDialog<Map<String, String>>(context: context, builder: (ctx) => AlertDialog(
      title: Text(old == null ? 'Новый промпт' : 'Редактировать промпт'),
      content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(controller: title, decoration: const InputDecoration(labelText: 'Название')),
        TextField(controller: category, decoration: const InputDecoration(labelText: 'Категория')),
        TextField(controller: prompt, minLines: 4, maxLines: 10, decoration: const InputDecoration(labelText: 'Текст промпта')),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Отмена')), FilledButton(onPressed: () {
        if (title.text.trim().isNotEmpty && prompt.text.trim().isNotEmpty) Navigator.pop(ctx, {'title':title.text.trim(),'category':category.text.trim().isEmpty ? 'Мои промпты' : category.text.trim(),'prompt':prompt.text.trim()});
      }, child: const Text('Сохранить'))],
    ));
    title.dispose(); category.dispose(); prompt.dispose();
    if (value == null || !mounted) return;
    setState(() { if (old == null) { _items.insert(0, value); } else { final i = _items.indexOf(old); if (i >= 0) _items[i] = value; } });
    await _save();
  }
  Future<void> _delete(Map<String, String> item) async {
    final ok = await showDialog<bool>(context: context, builder: (ctx) => AlertDialog(title: const Text('Удалить промпт?'), content: Text(item['title'] ?? ''), actions: [
      TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Отмена')),
      FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Удалить')),
    ]));
    if (ok != true || !mounted) return;
    setState(() => _items.remove(item)); await _save();
  }
  @override
  void dispose() { _search.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) {
    final visible = _visible;
    return Scaffold(
      appBar: AppBar(title: const Text('Библиотека промптов'), actions: [IconButton(tooltip: 'Добавить промпт', onPressed: () => _edit(), icon: const Icon(Icons.add))]),
      body: !_ready ? const Center(child: CircularProgressIndicator()) : Column(children: [
        Padding(padding: const EdgeInsets.all(12), child: TextField(controller: _search, onChanged: (_) => setState(() {}), decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Поиск по всем промптам', border: OutlineInputBorder()))),
        Padding(padding: const EdgeInsets.symmetric(horizontal: 12), child: Align(alignment: Alignment.centerLeft, child: Text('Всего промптов: ${_items.length}'))),
        Expanded(child: visible.isEmpty ? const Center(child: Text('Ничего не найдено')) : ListView.builder(itemCount: visible.length, itemBuilder: (ctx, i) {
          final item = visible[i];
          return Card(margin: const EdgeInsets.fromLTRB(12, 5, 12, 5), child: ListTile(
            title: Text(item['title'] ?? ''),
            subtitle: Text('${item['category'] ?? ''}\n${item['prompt'] ?? ''}', maxLines: 3, overflow: TextOverflow.ellipsis),
            isThreeLine: true,
            onTap: () => Navigator.pop(context, item['prompt']),
            trailing: PopupMenuButton<String>(onSelected: (v) { if (v == 'edit') _edit(item); if (v == 'delete') _delete(item); }, itemBuilder: (_) => const [PopupMenuItem(value:'edit', child:Text('Изменить')), PopupMenuItem(value:'delete', child:Text('Удалить'))]),
          ));
        })),
        const Padding(padding: EdgeInsets.all(12), child: Text('Нажмите на промпт, чтобы вставить его в чат. Свои промпты сохраняются на устройстве.', style: TextStyle(fontSize: 12, color: Colors.white60))),
      ]),
    );
  }
}
