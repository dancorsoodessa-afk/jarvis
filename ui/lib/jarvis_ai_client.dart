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
  JarvisIpc._({Process? process, HttpClient? httpClient, String? apiUrl, String? apiKey, String? model, String? fallbackApiUrl, String? fallbackApiKey, String? fallbackModel}) : _process = process, _httpClient = httpClient, _apiUrl = apiUrl, _apiKey = apiKey, _model = model, _fallbackApiUrl = fallbackApiUrl, _fallbackApiKey = fallbackApiKey, _fallbackModel = fallbackModel;
  static const _channel = MethodChannel('jarvis.voice');

  static Future<JarvisIpc> spawn(String executable, [List<String> args = const ['--ipc']]) async => JarvisIpc._(process: await Process.start(executable, args));
  static Future<JarvisIpc> connectAi(String apiUrl, {String model = '', String apiKey = '', String fallbackApiUrl = '', String fallbackModel = '', String fallbackApiKey = ''}) async {
    var url = apiUrl.trim().replaceFirst(RegExp(r'/+$'), '');
    for (final suffix in ['/chat/completions', '/models']) {
      if (url.endsWith(suffix)) { url = url.substring(0, url.length - suffix.length); break; }
    }
    if (url.isEmpty) throw ArgumentError('AI endpoint не указан');
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 15)..idleTimeout = const Duration(seconds: 60);
    final key = apiKey.trim().replaceFirst(RegExp(r'^(?:authorization\s*:\s*)?bearer\s+', caseSensitive: false), '').trim();
    var fallbackUrl = fallbackApiUrl.trim();
    while (fallbackUrl.endsWith('/')) fallbackUrl = fallbackUrl.substring(0, fallbackUrl.length - 1);
    for (final suffix in ['/chat/completions', '/models']) {
      if (fallbackUrl.endsWith(suffix)) { fallbackUrl = fallbackUrl.substring(0, fallbackUrl.length - suffix.length); break; }
    }
    final fallbackKey = fallbackApiKey.trim().replaceFirst(RegExp(r'^(?:authorization\s*:\s*)?bearer\s+', caseSensitive: false), '').trim();
    return JarvisIpc._(httpClient: client, apiUrl: url, apiKey: key, model: model.trim(), fallbackApiUrl: fallbackUrl.isEmpty ? null : fallbackUrl, fallbackApiKey: fallbackKey, fallbackModel: fallbackModel.trim());

  final Process? _process;
  final HttpClient? _httpClient;
  final String? _apiUrl;
  final String? _apiKey;
  final String? _model;
  final String? _fallbackApiUrl;
  final String? _fallbackApiKey;
  final String? _fallbackModel;
  /// Управление интерфейсом приложения (устанавливается экраном).
  Future<String> Function(String name, Map<String, dynamic> args)? uiHandler;
  final List<Map<String, dynamic>> _history = [];
  final Map<int, Completer<Map<String, dynamic>>> _pending = {};
  final _deltas = StreamController<Map<int, String>>.broadcast();
  bool _processListening = false;
  int _nextId = 0;
  int? _activeId;
  bool get _standalone => _httpClient != null;
  Stream<Map<int, String>> get deltas => _deltas.stream;
  int? get activeId => _activeId;
  Stream<String> partials() => deltas.map((m) => m[activeId]).where((value) => value != null).cast<String>();

  void _listenProcess() {
    if (_process == null || _processListening) return;
    _processListening = true;
    final acc = <int, String>{};
    _process!.stdout.transform(utf8.decoder).transform(const LineSplitter()).listen((line) {
      if (line.trim().isEmpty) return;
      try {
        final msg = jsonDecode(line) as Map<String, dynamic>;
        final id = msg['id'] is int ? msg['id'] as int : null;
        if (msg['type'] == 'delta' && id != null) {
          acc[id] = (acc[id] ?? '') + (msg['text']?.toString() ?? '');
          _deltas.add({id: acc[id]!});
        } else if (id != null) {
          final c = _pending.remove(id);
          if (c != null && !c.isCompleted) c.complete(msg);
        }
      } catch (e) {
        for (final c in _pending.values) { if (!c.isCompleted) c.completeError(e); }
        _pending.clear();
      }
    }, onError: (Object e) {
      for (final c in _pending.values) { if (!c.isCompleted) c.completeError(e); }
      _pending.clear();
    });
  }

  Future<Map<String, dynamic>> _ipc(Map<String, dynamic> body) {
    _listenProcess();
    final id = _nextId++;
    _activeId = id;
    final c = Completer<Map<String, dynamic>>();
    _pending[id] = c;
    _process!.stdin.writeln(jsonEncode({...body, 'id': id}));
    return c.future.timeout(const Duration(seconds: 90));
  }

  void _auth(HttpClientRequest r) {
    final key = _apiKey?.trim() ?? '';
    if (key.isNotEmpty) {
      r.headers.set(HttpHeaders.authorizationHeader, 'Bearer $key');
      r.headers.set('X-API-Key', key);
    }
  }

  Future<Map<String, dynamic>> _json(HttpClientResponse response) async {
    final body = await utf8.decoder.bind(response).join().timeout(const Duration(seconds: 90));
    dynamic value;
    try { value = body.trim().isEmpty ? <String, dynamic>{} : jsonDecode(body); } catch (_) { value = {'message': body.trim()}; }
    final data = value is Map<String, dynamic> ? value : <String, dynamic>{'data': value};
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final err = data['error'];
      final msg = err is Map ? err['message']?.toString() : data['message']?.toString();
      throw StateError('AI ${response.statusCode}: ${msg?.isNotEmpty == true ? msg : 'HTTP ${response.statusCode}'}');
    }
    return data;
  }

  Future<String> _modelId() async {
    if ((_model ?? '').trim().isNotEmpty) return _model!.trim();
    final r = await _httpClient!.getUrl(Uri.parse('$_apiUrl/models'));
    _auth(r);
    r.headers.set(HttpHeaders.acceptHeader, 'application/json');
    final data = (await _json(await r.close()))['data'];
    if (data is List) {
      for (final item in data) {
        if (item is Map && item['id']?.toString().trim().isNotEmpty == true) return item['id'].toString().trim();
      }
    }
    throw StateError('AI-сервер не сообщил доступную модель.');
  }

  static Map<String, dynamic> _fn(String name, String description, Map<String, dynamic> props, List<String> required) => {'type': 'function', 'function': {'name': name, 'description': description, 'parameters': {'type': 'object', 'properties': props, 'required': required}}};

  List<Map<String, dynamic>> _tools() => [
    _fn('google_search', 'Поиск в интернете (DuckDuckGo/Google): новости, факты, всё актуальное', {'query': {'type': 'string'}, 'limit': {'type': 'integer'}}, ['query']),
    _fn('web_get', 'Получить страницу HTTP/HTTPS', {'url': {'type': 'string'}}, ['url']),
    _fn('http_request', 'HTTP API GET/POST/PUT/PATCH/DELETE', {'method': {'type': 'string'}, 'url': {'type': 'string'}, 'body': {'type': 'string'}, 'headers': {'type': 'string'}}, ['url']),
    _fn('download_file', 'Скачать файл в app-specific storage', {'url': {'type': 'string'}, 'filename': {'type': 'string'}}, ['url']),
    _fn('weather', 'Погода через бесплатный Open-Meteo', {'city': {'type': 'string'}}, ['city']),
    _fn('file_roots', 'Доступные папки', {}, []),
    _fn('file_list', 'Список файлов', {'path': {'type': 'string'}}, []),
    _fn('file_read', 'Прочитать UTF-8 файл', {'path': {'type': 'string'}}, ['path']),
    _fn('file_write', 'Записать UTF-8 файл', {'path': {'type': 'string'}, 'content': {'type': 'string'}}, ['path', 'content']),
    _fn('file_append', 'Добавить в файл', {'path': {'type': 'string'}, 'content': {'type': 'string'}}, ['path', 'content']),
    _fn('file_mkdir', 'Создать папку', {'path': {'type': 'string'}}, ['path']),
    _fn('file_delete', 'Удалить файл/папку', {'path': {'type': 'string'}}, ['path']),
    _fn('file_copy', 'Копировать', {'from': {'type': 'string'}, 'to': {'type': 'string'}}, ['from', 'to']),
    _fn('file_move', 'Переместить', {'from': {'type': 'string'}, 'to': {'type': 'string'}}, ['from', 'to']),
    _fn('db_tables', 'Таблицы SQLite', {'database': {'type': 'string'}}, ['database']),
    _fn('db_query', 'SQLite SELECT/PRAGMA', {'database': {'type': 'string'}, 'sql': {'type': 'string'}, 'limit': {'type': 'integer'}}, ['database', 'sql']),
    _fn('db_exec', 'SQLite INSERT/UPDATE/DDL', {'database': {'type': 'string'}, 'sql': {'type': 'string'}}, ['database', 'sql']),
    _fn('device_info', 'Информация Android', {}, []),
    _fn('time_now', 'Текущее время', {}, []),
    _fn('open_url', 'Открыть HTTP/HTTPS ссылку', {'url': {'type': 'string'}}, ['url']),
    _fn('clipboard_get', 'Прочитать буфер', {}, []),
    _fn('clipboard_set', 'Записать буфер', {'text': {'type': 'string'}}, ['text']),
    _fn('ui_set_theme', 'Сменить цвет интерфейса (акцент): название цвета или #RRGGBB', {'color': {'type': 'string'}}, ['color']),
    _fn('ui_set_text_scale', 'Размер текста интерфейса от 0.8 до 1.6', {'scale': {'type': 'number'}}, ['scale']),
    _fn('ui_set_orb_height', 'Высота анимированного ядра в пикселях от 160 до 420', {'height': {'type': 'number'}}, ['height']),
    _fn('ui_set_voice', 'Включить или выключить голосовой режим', {'enabled': {'type': 'boolean'}}, ['enabled']),
    _fn('ui_set_wake_word', 'Требовать ли обращение «Джарвис» перед командой', {'required': {'type': 'boolean'}}, ['required']),
    _fn('ui_open_settings', 'Открыть экран настроек', {}, []),
    _fn('ui_reset', 'Сбросить внешний вид к стандартному', {}, []),
    _fn('ui_get_state', 'Текущие параметры интерфейса', {}, []),
    _fn('self_improve', 'Изменить постоянное поведение БУСИ', {'instruction': {'type': 'string'}}, ['instruction']),
    _fn('self_learn', 'Сохранить правило/навык/предпочтение', {'category': {'type': 'string'}, 'text': {'type': 'string'}, 'priority': {'type': 'integer'}}, ['text']),
    _fn('self_forget', 'Забыть правило', {'text': {'type': 'string'}}, ['text']),
    _fn('self_memory', 'Полная память самоулучшения', {}, []),
    _fn('self_behavior', 'Активный поведенческий слой', {}, []),
    _fn('self_clear', 'Полностью очистить память самоулучшения', {}, []),
  ];

  Future<String> _tool(String name, Map<String, dynamic> args) async {
    if (name.startsWith('ui_')) {
      final h = uiHandler;
      if (h == null) throw StateError('Управление интерфейсом недоступно');
      return await h(name, args);
    }
    if (!Platform.isAndroid) throw StateError('Android-инструмент недоступен');
    return (await _channel.invokeMethod<dynamic>('android_tool', {'name': name, 'args': jsonEncode(args)}))?.toString() ?? '';
  }

  Future<JarvisReply> _local(String text) async {
    if (!Platform.isAndroid) return JarvisReply('', 'none', null, false);
    final lower = text.trim().toLowerCase();
    if (lower == 'что ты помнишь' || lower == 'чему ты научилась' || lower == 'покажи память') return JarvisReply(await _tool('self_memory', {}), 'android-self-improvement', 'self_memory', false);
    if (lower == 'покажи правила' || lower == 'какое у тебя поведение') return JarvisReply(await _tool('self_behavior', {}), 'android-self-improvement', 'self_behavior', false);
    for (final p in ['запомни ', 'запомни:', 'научись:']) {
      if (lower.startsWith(p)) {
        final t = text.trim().substring(p.length).trim();
        if (t.isEmpty) return JarvisReply('Скажи, что запомнить.', 'android-self-improvement', null, false);
        await _tool('self_learn', {'category': 'rules', 'text': t, 'priority': 95});
        return JarvisReply('Запомнила и активировала правило.', 'android-self-improvement', 'self_learn', false);
      }
    }
    for (final p in ['самоулучшайся:', 'самоулучшись:', 'самоулучшайся ', 'самоулучшись ', 'самоулучшайся', 'самоулучшись']) {
      if (lower.startsWith(p)) {
        final t = text.trim().substring(p.length).trim();
        final raw = await _tool('self_improve', {'instruction': t.isEmpty ? 'Проведи максимальное безопасное улучшение поведения, памяти, инструментов и обработки ошибок.' : t});
        return JarvisReply('Самоулучшение применено. Состояние: ${_version(raw)}', 'android-self-improvement', 'self_improve', false);
      }
    }
    for (final p in ['забудь ', 'забудь:']) {
      if (lower.startsWith(p)) {
        await _tool('self_forget', {'text': text.trim().substring(p.length).trim()});
        return JarvisReply('Правило удалено.', 'android-self-improvement', 'self_forget', false);
      }
    }
    return JarvisReply('', 'none', null, false);
  }

  String _version(String raw) { try { return (jsonDecode(raw) as Map)['version']?.toString() ?? '?'; } catch (_) { return '?'; } }

  Future<String> _transcribeAttachment(Map<String, dynamic> attachment) async {
    final mime = (attachment['mime']?.toString() ?? '').toLowerCase();
    final data = attachment['data']?.toString() ?? '';
    if (data.isEmpty) throw StateError('Пустой аудиофайл');
    String format = 'wav';
    if (mime.contains('mpeg') || mime.endsWith('/mp3')) format = 'mp3';
    else if (mime.contains('m4a')) format = 'm4a';
    else if (mime.contains('ogg')) format = 'ogg';
    else if (mime.contains('webm')) format = 'webm';
    else if (mime.contains('aac')) format = 'aac';
    final req = await _httpClient!.postUrl(Uri.parse('$_apiUrl/audio/transcriptions'));
    req.headers.contentType = ContentType.json;
    _auth(req);
    req.write(jsonEncode({
      'model': 'openai/whisper-1',
      'input_audio': {'data': data, 'format': format},
      'language': 'ru',
    }));
    final decoded = await _json(await req.close());
    final text = decoded['text']?.toString().trim() ?? '';
    if (text.isEmpty) throw StateError('STT не вернул текст');
    return text;
  }

  List<Map<String, dynamic>> _attachmentParts(Map<String, dynamic> a, String prompt) {
    final name = a['name']?.toString() ?? 'file';
    final mime = (a['mime']?.toString() ?? 'application/octet-stream').toLowerCase();
    final data = a['data']?.toString() ?? '';
    if (mime.startsWith('image/')) {
      return [
        {'type': 'text', 'text': prompt},
        {'type': 'image_url', 'image_url': {'url': 'data:$mime;base64,$data'}},
      ];
    }
    if (mime.startsWith('video/')) {
      return [
        {'type': 'text', 'text': prompt},
        {'type': 'video_url', 'video_url': {'url': 'data:$mime;base64,$data'}},
      ];
    }
    if (mime == 'application/pdf') {
      return [
        {'type': 'text', 'text': prompt},
        {'type': 'file', 'file': {'filename': name, 'file_data': 'data:$mime;base64,$data'}},
      ];
    }
    if (mime.startsWith('text/') || mime.contains('json') || mime.contains('csv') || mime.contains('xml') || mime.contains('markdown')) {
      try {
        final decoded = utf8.decode(base64Decode(data));
        return [{'type': 'text', 'text': '$prompt\n\nФайл $name:\n$decoded'}];
      } catch (_) {}
    }
    return [
      {'type': 'text', 'text': '$prompt\n\nПрикреплён файл: $name ($mime).'},
    ];
  }

  Future<JarvisReply> _standaloneSend(String text, {Map<String, dynamic>? attachment}) async {
    var userText = text;
    Map<String, dynamic>? activeAttachment = attachment;
    if (attachment != null && (attachment['mime']?.toString() ?? '').toLowerCase().startsWith('audio/')) {
      userText = '$text\n\nРасшифровка прикреплённого аудио: ${await _transcribeAttachment(attachment)}';
      activeAttachment = null;
    }
    final local = await _local(userText);
    if (local.text.isNotEmpty) return local;
    final defaultModel = await _modelId();
    final attachmentMime = (activeAttachment?['mime']?.toString() ?? '').toLowerCase();
    final model = activeAttachment != null ? 'google/gemma-4-26b-a4b-it:free' : defaultModel;
    var activeApiUrl = _apiUrl!;
    var activeApiKey = _apiKey ?? '';
    var activeModel = model;
    var usingFallback = false;
    final behavior = Platform.isAndroid ? await _tool('self_behavior', {}) : '';
    final system = 'Ты JARVIS — голосовой AI-ассистент. Отвечай на языке пользователя кратко: 1–3 предложения, если не просят подробно. Для реальных действий используй инструменты, не выдумывай результат. Интернет: google_search (актуальная информация, новости), web_get, weather. Интерфейс: ты сам меняешь экран через ui_* (цвет, размер текста, размер ядра, голос, настройки) — когда просят изменить вид или настройки, вызови нужный ui_*. Самоулучшение — постоянные правила через self_improve/self_learn. Не заявляй об изменении весов модели или APK. Активный слой:\n$behavior';
    final messages = <Map<String, dynamic>>[{'role': 'system', 'content': system}, ..._history, {'role': 'user', 'content': activeAttachment == null ? userText : _attachmentParts(activeAttachment, userText)}];
    String answer = '';
    String? lastTool;
    String responseModel = model;
    for (var round = 0; round < 8; round++) {
      while (true) {
        final req = await _httpClient!.postUrl(Uri.parse('${activeApiUrl}/chat/completions'));
        req.headers.contentType = ContentType.json;
        req.headers.set(HttpHeaders.acceptHeader, 'application/json');
        if (activeApiUrl.contains('openrouter.ai')) {
          req.headers.set('HTTP-Referer', 'https://github.com/dancorsoodessa-afk/jarvis');
          req.headers.set('X-OpenRouter-Title', 'JARVIS Android');
        }
        if (activeApiKey.trim().isNotEmpty) {
          req.headers.set(HttpHeaders.authorizationHeader, 'Bearer ${activeApiKey.trim()}');
          req.headers.set('X-API-Key', activeApiKey.trim());
        }
        final models = <String>[activeModel, 'openrouter/free'].where((m) => m.trim().isNotEmpty).toSet().toList();
        final requestBody = <String, dynamic>{
          'messages': messages,
          'tools': _tools(),
          'tool_choice': 'auto',
          'temperature': 0.2,
          'stream': false,
          'max_tokens': 700,
        };
        if (activeApiUrl.contains('openrouter.ai')) {
          requestBody['reasoning'] = {'enabled': false};
          requestBody['models'] = models;
        } else {
          requestBody['model'] = activeModel;
        }
        req.write(jsonEncode(requestBody));
        try {
          final decoded = await _json(await req.close());
          responseModel = decoded['model']?.toString() ?? activeModel;
        answer = answer.trim().isEmpty ? 'Готово.' : answer.trim();
    _history.add({'role': 'user', 'content': userText});
    _history.add({'role': 'assistant', 'content': answer});
    while (_history.length > 12) _history.removeAt(0);
    if (Platform.isAndroid) {
      try { await _channel.invokeMethod('self_feedback', {'user': text, 'assistant': answer}); } catch (_) {}
    }
    return JarvisReply(answer, responseModel, lastTool, false);
  }

  Future<void> verifyConnection() async {
    if (!_standalone) return;
    Future<void> check(String url, String key) async {
      final r = await _httpClient!.getUrl(Uri.parse('${url.replaceFirst(RegExp(r'/+

  Future<JarvisReply> sendMessage(String text, {Map<String, dynamic>? attachment}) async {
    if (_standalone) return await _standaloneSend(text, attachment: attachment);
    final response = await _ipc({
      'type': 'message',