import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/services.dart';

class JarvisReply {
  JarvisReply(this.text, this.provider, this.toolUsed, this.needsConfirmation);
  factory JarvisReply.fromJson(Map<String, dynamic> json) => JarvisReply(json['text']?.toString() ?? '', json['provider']?.toString() ?? 'unknown', json['tool_used']?.toString(), json['needs_confirmation'] == true);
  final String text;
  final String provider;
  final String? toolUsed;
  final bool needsConfirmation;
}

class JarvisIpc {
  JarvisIpc._({Process? process, HttpClient? httpClient, String? apiUrl, String? apiKey, String? model}) : _process = process, _httpClient = httpClient, _apiUrl = apiUrl, _apiKey = apiKey, _model = model;
  static const _channel = MethodChannel('busya.voice');

  static Future<JarvisIpc> spawn(String executable, [List<String> args = const ['--ipc']]) async => JarvisIpc._(process: await Process.start(executable, args));
  static Future<JarvisIpc> connectAi(String apiUrl, {String model = '', String apiKey = ''}) async {
    var url = apiUrl.trim().replaceFirst(RegExp(r'/+$'), '');
    for (final suffix in ['/chat/completions', '/models']) if (url.endsWith(suffix)) { url = url.substring(0, url.length - suffix.length); break; }
    if (url.isEmpty) throw ArgumentError('AI endpoint не указан');
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 15)..idleTimeout = const Duration(seconds: 60);
    final key = apiKey.trim().replaceFirst(RegExp(r'^(?:authorization\s*:\s*)?bearer\s+', caseSensitive: false), '').trim();
    return JarvisIpc._(httpClient: client, apiUrl: url, apiKey: key, model: model.trim());
  }

  final Process? _process;
  final HttpClient? _httpClient;
  final String? _apiUrl;
  final String? _apiKey;
  final String? _model;
  final List<Map<String, dynamic>> _history = [];
  final Map<int, Completer<Map<String, dynamic>>> _pending = {};
  final _deltas = StreamController<Map<int, String>>.broadcast();
  bool _processListening = false;
  int _nextId = 0;
  int? _activeId;
  bool get _standalone => _httpClient != null;
  Stream<Map<int, String>> get deltas => _deltas.stream;
  int? get activeId => _activeId;
  Stream<String> partials() => deltas.map((m) => m[activeId]).whereType<String>();

  void _listenProcess() {
    if (_process == null || _processListening) return;
    _processListening = true;
    final acc = <int, String>{};
    _process.stdout.transform(utf8.decoder).transform(const LineSplitter()).listen((line) {
      if (line.trim().isEmpty) return;
      try {
        final msg = jsonDecode(line) as Map<String, dynamic>;
        final id = msg['id'] is int ? msg['id'] as int : null;
        if (msg['type'] == 'delta' && id != null) { acc[id] = (acc[id] ?? '') + (msg['text']?.toString() ?? ''); _deltas.add({id: acc[id]!}); }
        else if (id != null) { final c = _pending.remove(id); if (c != null && !c.isCompleted) c.complete(msg); }
      } catch (e) { for (final c in _pending.values) if (!c.isCompleted) c.completeError(e); _pending.clear(); }
    }, onError: (Object e) { for (final c in _pending.values) if (!c.isCompleted) c.completeError(e); _pending.clear(); });
  }

  Future<Map<String, dynamic>> _ipc(Map<String, dynamic> body) {
    _listenProcess();
    final id = _nextId++; _activeId = id; final c = Completer<Map<String, dynamic>>(); _pending[id] = c;
    _process!.stdin.writeln(jsonEncode({...body, 'id': id}));
    return c.future.timeout(const Duration(seconds: 90));
  }

  void _auth(HttpClientRequest r) { final key = _apiKey?.trim() ?? ''; if (key.isNotEmpty) { r.headers.set(HttpHeaders.authorizationHeader, 'Bearer $key'); r.headers.set('X-API-Key', key); } }

  Future<Map<String, dynamic>> _json(HttpClientResponse response) async {
    final body = await utf8.decoder.bind(response).join().timeout(const Duration(seconds: 90));
    dynamic value; try { value = body.trim().isEmpty ? <String, dynamic>{} : jsonDecode(body); } catch (_) { value = {'message': body.trim()}; }
    final data = value is Map<String, dynamic> ? value : <String, dynamic>{'data': value};
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final err = data['error']; final msg = err is Map ? err['message']?.toString() : data['message']?.toString();
      throw StateError('AI ${response.statusCode}: ${msg?.isNotEmpty == true ? msg : 'HTTP ${response.statusCode}'}');
    }
    return data;
  }

  Future<String> _modelId() async {
    if ((_model ?? '').trim().isNotEmpty) return _model!.trim();
    final r = await _httpClient!.getUrl(Uri.parse('$_apiUrl/models')); _auth(r); r.headers.set(HttpHeaders.acceptHeader, 'application/json');
    final data = (await _json(await r.close()))['data'];
    if (data is List) for (final item in data) if (item is Map && item['id']?.toString().trim().isNotEmpty == true) return item['id'].toString().trim();
    throw StateError('AI-сервер не сообщил доступную модель.');
  }

  static Map<String, dynamic> _fn(String name, String description, Map<String, dynamic> props, List<String> required) => {'type': 'function', 'function': {'name': name, 'description': description, 'parameters': {'type': 'object', 'properties': props, 'required': required}}};
  List<Map<String, dynamic>> _tools() => [
    _fn('google_search', 'Основной поиск через Google.com', {'query': {'type': 'string'}, 'limit': {'type': 'integer'}}, ['query']),
    _fn('web_get', 'Получить страницу HTTP/HTTPS', {'url': {'type': 'string'}}, ['url']),
    _fn('http_request', 'HTTP API GET/POST/PUT/PATCH/DELETE', {'method': {'type': 'string'}, 'url': {'type': 'string'}, 'body': {'type': 'string'}, 'headers': {'type': 'string'}}, ['url']),
    _fn('download_file', 'Скачать файл в app-specific storage', {'url': {'type': 'string'}, 'filename': {'type': 'string'}}, ['url']),
    _fn('weather', 'Погода через бесплатный Open-Meteo', {'city': {'type': 'string'}}, ['city']),
    _fn('file_roots', 'Доступные папки', {}, []), _fn('file_list', 'Список файлов', {'path': {'type': 'string'}}, []),
    _fn('file_read', 'Прочитать UTF-8 файл', {'path': {'type': 'string'}}, ['path']), _fn('file_write', 'Записать UTF-8 файл', {'path': {'type': 'string'}, 'content': {'type': 'string'}}, ['path', 'content']),
    _fn('file_append', 'Добавить в файл', {'path': {'type': 'string'}, 'content': {'type': 'string'}}, ['path', 'content']), _fn('file_mkdir', 'Создать папку', {'path': {'type': 'string'}}, ['path']),
    _fn('file_delete', 'Удалить файл/папку', {'path': {'type': 'string'}}, ['path']), _fn('file_copy', 'Копировать', {'from': {'type': 'string'}, 'to': {'type': 'string'}}, ['from', 'to']), _fn('file_move', 'Переместить', {'from': {'type': 'string'}, 'to': {'type': 'string'}}, ['from', 'to']),
    _fn('db_tables', 'Таблицы SQLite', {'database': {'type': 'string'}}, ['database']), _fn('db_query', 'SQLite SELECT/PRAGMA', {'database': {'type': 'string'}, 'sql': {'type': 'string'}, 'limit': {'type': 'integer'}}, ['database', 'sql']), _fn('db_exec', 'SQLite INSERT/UPDATE/DDL', {'database': {'type': 'string'}, 'sql': {'type': 'string'}}, ['database', 'sql']),
    _fn('device_info', 'Информация Android', {}, []), _fn('time_now', 'Текущее время', {}, []), _fn('open_url', 'Открыть HTTP/HTTPS ссылку', {'url': {'type': 'string'}}, ['url']), _fn('clipboard_get', 'Прочитать буфер', {}, []), _fn('clipboard_set', 'Записать буфер', {'text': {'type': 'string'}}, ['text']),
    _fn('self_improve', 'Изменить постоянное поведение БУСИ', {'instruction': {'type': 'string'}}, ['instruction']), _fn('self_learn', 'Сохранить правило/навык/предпочтение', {'category': {'type': 'string'}, 'text': {'type': 'string'}, 'priority': {'type': 'integer'}}, ['text']), _fn('self_forget', 'Забыть правило', {'text': {'type': 'string'}}, ['text']), _fn('self_memory', 'Полная память самоулучшения', {}, []), _fn('self_behavior', 'Активный поведенческий слой', {}, []),
  ];

  Future<String> _tool(String name, Map<String, dynamic> args) async {
    if (!Platform.isAndroid) throw StateError('Android-инструмент недоступен');
    return (await _channel.invokeMethod<dynamic>('android_tool', {'name': name, 'args': jsonEncode(args)}))?.toString() ?? '';
  }

  Future<JarvisReply> _local(String text) async {
    if (!Platform.isAndroid) return JarvisReply('', 'none', null, false);
    final lower = text.trim().toLowerCase();
    if (lower == 'что ты помнишь' || lower == 'чему ты научилась' || lower == 'покажи память') return JarvisReply(await _tool('self_memory', {}), 'android-self-improvement', 'self_memory', false);
    if (lower == 'покажи правила' || lower == 'какое у тебя поведение') return JarvisReply(await _tool('self_behavior', {}), 'android-self-improvement', 'self_behavior', false);
    for (final p in ['запомни ', 'запомни:', 'научись:']) if (lower.startsWith(p)) { final t = text.trim().substring(p.length).trim(); if (t.isEmpty) return JarvisReply('Скажи, что запомнить.', 'android-self-improvement', null, false); await _tool('self_learn', {'category': 'rules', 'text': t, 'priority': 95}); return JarvisReply('Запомнила и активировала правило.', 'android-self-improvement', 'self_learn', false); }
    for (final p in ['самоулучшайся:', 'самоулучшись:', 'самоулучшайся ', 'самоулучшись ', 'самоулучшайся', 'самоулучшись']) if (lower.startsWith(p)) { final t = text.trim().substring(p.length).trim(); final raw = await _tool('self_improve', {'instruction': t.isEmpty ? 'Проведи максимальное безопасное улучшение поведения, памяти, инструментов и обработки ошибок.' : t}); return JarvisReply('Самоулучшение применено. Состояние: ${_version(raw)}', 'android-self-improvement', 'self_improve', false); }
    for (final p in ['забудь ', 'забудь:']) if (lower.startsWith(p)) { await _tool('self_forget', {'text': text.trim().substring(p.length).trim()}); return JarvisReply('Правило удалено.', 'android-self-improvement', 'self_forget', false); }
    return JarvisReply('', 'none', null, false);
  }
  String _version(String raw) { try { return (jsonDecode(raw) as Map)['version']?.toString() ?? '?'; } catch (_) { return '?'; } }

  Future<JarvisReply> _standaloneSend(String text) async {
    final local = await _local(text); if (local.text.isNotEmpty) return local;
    final model = await _modelId();
    final behavior = Platform.isAndroid ? await _tool('self_behavior', {}) : '';
    final system = 'Ты БУСЯ — автономный AI-агент. Отвечай на языке пользователя. Используй инструменты для реальных действий и не выдумывай результат. Отделы инструментов: internet (Google.com, HTTP, download, weather), files, database (SQLite), other, self-improvement. Самоулучшение — изменение постоянного поведенческого слоя: правила, навыки, предпочтения, исправления, успешные шаблоны и политики инструментов. Когда пользователь просит улучшить себя — используй self_improve или self_learn. Не заявляй об изменении весов модели или подписанного APK. Активный слой:\n$behavior';
    final messages = <Map<String, dynamic>>[{'role': 'system', 'content': system}, ..._history, {'role': 'user', 'content': text}];
    String answer = ''; String? lastTool;
    for (var round = 0; round < 8; round++) {
      final req = await _httpClient!.postUrl(Uri.parse('$_apiUrl/chat/completions')); req.headers.contentType = ContentType.json; req.headers.set(HttpHeaders.acceptHeader, 'application/json'); _auth(req);
      req.write(jsonEncode({'model': model, 'messages': messages, 'tools': _tools(), 'tool_choice': 'auto', 'temperature': 0.2, 'stream': false}));
      final decoded = await _json(await req.close()); final choices = decoded['choices']; if (choices is! List || choices.isEmpty) throw StateError('AI не вернул choices');
      final message = choices.first is Map ? choices.first['message'] : null; if (message is! Map) throw StateError('AI не вернул message');
      final content = message['content']; if (content != null) answer = content.toString();
      final calls = message['tool_calls']; if (calls is! List || calls.isEmpty) break;
      messages.add({'role': 'assistant', 'content': content, 'tool_calls': calls});
      for (final call in calls) {
        if (call is! Map || call['function'] is! Map) continue;
        final fn = call['function'] as Map; final name = fn['name']?.toString() ?? ''; Map<String, dynamic> args = {};
        try { final a = jsonDecode(fn['arguments']?.toString() ?? '{}'); if (a is Map) args = Map<String, dynamic>.from(a); } catch (_) {}
        String result; try { result = await _tool(name, args); lastTool = name; } catch (e) { result = jsonEncode({'error': e.toString()}); }
        messages.add({'role': 'tool', 'tool_call_id': call['id']?.toString() ?? name, 'content': result});
      }
    }
    answer = answer.trim().isEmpty ? 'Готово.' : answer.trim();
    _history.add({'role': 'user', 'content': text}); _history.add({'role': 'assistant', 'content': answer}); while (_history.length > 24) _history.removeAt(0);
    if (Platform.isAndroid) { try { await _channel.invokeMethod('self_feedback', {'user': text, 'assistant': answer}); } catch (_) {} }
    return JarvisReply(answer, model, lastTool, false);
  }

  Future<JarvisReply> sendMessage(String text) async => _standalone ? _standaloneSend(text) : JarvisReply.fromJson(await _ipc({'type': 'chat', 'text': text}));

  Future<List<String>> listTools() async {
    if (!_standalone) { try { final r = await _ipc({'type': 'list_tools'}); if (r['tools'] is List) return (r['tools'] as List).map((e) => e.toString()).toList(); } catch (_) {} return const []; }
    return _tools().map((x) => ((x['function'] as Map)['name'] ?? '').toString()).where((x) => x.isNotEmpty).toList();
  }

  Future<void> dispose() async { for (final c in _pending.values) if (!c.isCompleted) c.completeError(StateError('Клиент закрыт')); _pending.clear(); await _deltas.close(); _httpClient?.close(force: true); _process?.kill(); }
}
