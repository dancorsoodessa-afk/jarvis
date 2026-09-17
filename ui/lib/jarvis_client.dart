import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

class JarvisReply {
  JarvisReply(this.text, this.provider, this.toolUsed, this.needsConfirmation);
  factory JarvisReply.fromJson(Map<String, dynamic> json) => JarvisReply(
        json['text'] as String,
        json['provider'] as String? ?? 'unknown',
        json['tool_used'] as String?,
        json['needs_confirmation'] as bool? ?? false,
      );
  final String text;
  final String provider;
  final String? toolUsed;
  final bool needsConfirmation;
}

class JarvisIpc {
  JarvisIpc._({Process? process, HttpClient? httpClient, String? apiUrl, String? apiKey, String? model})
      : _process = process,
        _httpClient = httpClient,
        _apiUrl = apiUrl,
        _apiKey = apiKey,
        _model = model;

  static const _memoryChannel = MethodChannel('busya.voice');

  static Future<JarvisIpc> spawn(String executable, [List<String> args = const ['--ipc']]) async {
    final process = await Process.start(executable, args);
    return JarvisIpc._(process: process);
  }

  static Future<JarvisIpc> connectAi(String apiUrl, {String model = '', String apiKey = ''}) async {
    var normalized = apiUrl.trim().replaceFirst(RegExp(r'/+$'), '');
    for (final suffix in ['/chat/completions', '/models']) {
      if (normalized.endsWith(suffix)) {
        normalized = normalized.substring(0, normalized.length - suffix.length);
        break;
      }
    }
    if (normalized.isEmpty) throw ArgumentError('AI endpoint не указан');
    var normalizedKey = apiKey.trim();
    final authPrefix = RegExp(r'^(?:authorization\s*:\s*)?bearer\s+', caseSensitive: false);
    normalizedKey = normalizedKey.replaceFirst(authPrefix, '').trim();
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 15)
      ..idleTimeout = const Duration(seconds: 60);
    return JarvisIpc._(httpClient: client, apiUrl: normalized, apiKey: normalizedKey, model: model.trim());
  }

  final Process? _process;
  final HttpClient? _httpClient;
  final String? _apiUrl;
  final String? _apiKey;
  final String? _model;
  int _nextId = 0;
  int? _activeId;
  bool _listening = false;
  final Map<int, Completer<Map<String, dynamic>>> _pending = {};
  final _deltaController = StreamController<Map<int, String>>.broadcast();
  final List<Map<String, String>> _history = [];
  List<String>? _learning;
  List<String>? _lastTools;
  bool get _standalone => _httpClient != null;
  Stream<Map<int, String>> get deltas => _deltaController.stream;
  int? get activeId => _activeId;
  Stream<String> partials() => deltas.map((m) => m[activeId]).where((value) => value != null).cast<String>();

  void _ensureListening() {
    if (_standalone || _listening) return;
    _listening = true;
    final accumulated = <int, String>{};
    _process!.stdout.transform(utf8.decoder).transform(const LineSplitter()).listen((line) {
      if (line.trim().isEmpty) return;
      final msg = jsonDecode(line) as Map<String, dynamic>;
      final id = msg['id'] is int ? msg['id'] as int : null;
      if (msg['type'] == 'delta' && id != null) {
        accumulated[id] = (accumulated[id] ?? '') + (msg['text'] as String);
        _deltaController.add({id: accumulated[id]!});
        return;
      }
      final completer = id == null ? null : _pending.remove(id);
      completer?.complete(msg);
    }, onError: (Object error) {
      for (final c in _pending.values) {
        if (!c.isCompleted) c.completeError(error);
      }
      _pending.clear();
    });
  }

  void _write(Map<String, dynamic> body) => _process!.stdin.writeln(jsonEncode(body));

  Future<Map<String, dynamic>> _request(Map<String, dynamic> body) {
    _ensureListening();
    final id = _nextId++;
    _activeId = id;
    final completer = Completer<Map<String, dynamic>>();
    _pending[id] = completer;
    _write({...body, 'id': id});
    return completer.future;
  }

  void _setAuth(HttpClientRequest request) {
    final key = _apiKey?.trim() ?? '';
    if (key.isEmpty) return;
    request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $key');
    request.headers.set('X-API-Key', key);
  }

  Future<Map<String, dynamic>> _jsonResponse(HttpClientResponse response) async {
    final body = await utf8.decoder.bind(response).join();
    Map<String, dynamic> decoded = <String, dynamic>{};
    if (body.trim().isNotEmpty) {
      try {
        final value = jsonDecode(body);
        if (value is Map<String, dynamic>) decoded = value;
      } catch (_) {
        decoded = {'message': body.trim()};
      }
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final error = decoded['error'];
      final message = error is Map ? error['message']?.toString() : decoded['message']?.toString();
      throw StateError('AI ${response.statusCode}: ${message == null || message.isEmpty ? 'HTTP ${response.statusCode}' : message}');
    }
    return decoded;
  }

  Future<String> _resolveModel() async {
    if (_model != null && _model!.isNotEmpty) return _model!;
    final request = await _httpClient!.getUrl(Uri.parse('$_apiUrl/models'));
    request.headers.set(HttpHeaders.acceptHeader, 'application/json');
    _setAuth(request);
    final decoded = await _jsonResponse(await request.close());
    final data = decoded['data'];
    if (data is List) {
      for (final item in data) {
        if (item is Map && item['id'] is String && (item['id'] as String).trim().isNotEmpty) return (item['id'] as String).trim();
      }
    }
    throw StateError('AI-сервер не сообщил доступных моделей. Укажите модель вручную.');
  }

  Future<List<String>> _loadLearning() async {
    if (_learning != null) return List<String>.from(_learning!);
    if (!Platform.isAndroid) return _learning = <String>[];
    try {
      final raw = await _memoryChannel.invokeMethod<dynamic>('load_learning');
      _learning = raw is List ? raw.map((e) => e.toString()).where((e) => e.trim().isNotEmpty).toList() : <String>[];
    } catch (_) { _learning = <String>[]; }
    return List<String>.from(_learning!);
  }

  Future<void> _saveLearning() async {
    if (!Platform.isAndroid || _learning == null) return;
    try { await _memoryChannel.invokeMethod('save_learning', {'items': _learning}); } catch (_) {}
  }

  Future<JarvisReply> _learningCommand(String text) async {
    final lower = text.trim().toLowerCase();
    final items = await _loadLearning();
    const rememberPrefixes = ['запомни ', 'запомни:', 'научись:', 'самоулучшайся:', 'самоулучшись:'];
    for (final prefix in rememberPrefixes) {
      if (lower.startsWith(prefix)) {
        final lesson = text.trim().substring(prefix.length).trim();
        if (lesson.isEmpty) return JarvisReply('Скажи, чему именно мне самоулучшиться или что запомнить.', 'android-learning', null, false);
        if (!items.any((x) => x.toLowerCase() == lesson.toLowerCase())) items.add(lesson);
        _learning = items.takeLast(100).toList();
        await _saveLearning();
        return JarvisReply('Приняла изменение. Правило сохранено и будет использоваться дальше.', 'android-learning', null, false);
      }
    }
    if (lower == 'что ты запомнила' || lower == 'что ты помнишь' || lower == 'чему ты научилась' || lower == 'покажи память') {
      if (items.isEmpty) return JarvisReply('Пока ничего не сохранено.', 'android-learning', null, false);
      return JarvisReply('Мои сохранённые правила:\n${items.asMap().entries.map((e) => '${e.key + 1}. ${e.value}').join('\n')}', 'android-learning', null, false);
    }
    const forgetPrefixes = ['забудь ', 'забудь:'];
    for (final prefix in forgetPrefixes) {
      if (lower.startsWith(prefix)) {
        final target = text.trim().substring(prefix.length).trim().toLowerCase();
        final before = items.length;
        items.removeWhere((x) => x.toLowerCase().contains(target));
        _learning = items;
        await _saveLearning();
        return JarvisReply(before == items.length ? 'Такого правила в памяти не было.' : 'Забыла указанное правило.', 'android-learning', null, false);
      }
    }
    return JarvisReply('', 'none', null, false);
  }

  List<Map<String, dynamic>> _toolDefinitions() => [
        {
          'type': 'function',
          'function': {
            'name': 'web_search',
            'description': 'Ищет актуальную информацию в интернете. Используй для новостей, фактов, сайтов и свежих данных.',
            'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query']},
          },
        },
        {
          'type': 'function',
          'function': {
            'name': 'web_get',
            'description': 'Получает содержимое публичного HTTP/HTTPS URL в реальном времени.',
            'parameters': {'type': 'object', 'properties': {'url': {'type': 'string'}}, 'required': ['url']},
          },
        },
        {
          'type': 'function',
          'function': {
            'name': 'weather',
            'description': 'Получает текущую погоду по названию города через бесплатный Open-Meteo.',
            'parameters': {'type': 'object', 'properties': {'city': {'type': 'string'}}, 'required': ['city']},
          },
        },
      ];

  Future<String> _toolWebSearch(String query) async {
    final encoded = Uri.encodeQueryComponent(query);
    final request = await _httpClient!.getUrl(Uri.parse('https://html.duckduckgo.com/html/?q=$encoded'));
    request.headers.set(HttpHeaders.userAgentHeader, 'Mozilla/5.0');
    final response = await request.close();
    final body = await utf8.decoder.bind(response).join();
    if (response.statusCode < 200 || response.statusCode >= 300) throw StateError('Поиск HTTP ${response.statusCode}');
    final text = body.replaceAll(RegExp(r'<script[\\s\\S]*?</script>', caseSensitive: false), ' ')
        .replaceAll(RegExp(r'<style[\\s\\S]*?</style>', caseSensitive: false), ' ')
        .replaceAll(RegExp(r'<[^>]+>'), ' ')
        .replaceAll(RegExp(r'&(?:amp|quot|lt|gt|#39);'), ' ')
        .replaceAll(RegExp(r'\\s+'), ' ')
        .trim();
    return text.length > 7000 ? text.substring(0, 7000) : text;
  }

  Future<String> _toolWebGet(String url) async {
    final uri = Uri.parse(url);
    if (uri.scheme != 'http' && uri.scheme != 'https') throw ArgumentError('Разрешены только HTTP/HTTPS URL');
    final request = await _httpClient!.getUrl(uri);
    request.headers.set(HttpHeaders.userAgentHeader, 'Mozilla/5.0');
    final response = await request.close();
    final body = await utf8.decoder.bind(response).join();
    if (response.statusCode < 200 || response.statusCode >= 300) throw StateError('URL HTTP ${response.statusCode}');
    return body.length > 12000 ? body.substring(0, 12000) : body;
  }

  Future<String> _toolWeather(String city) async {
    final geoReq = await _httpClient!.getUrl(Uri.parse('https://geocoding-api.open-meteo.com/v1/search?name=${Uri.encodeQueryComponent(city)}&count=1&language=ru&format=json'));
    final geo = await _jsonResponse(await geoReq.close());
    final results = geo['results'];
    if (results is! List || results.isEmpty) throw StateError('Город не найден: $city');
    final place = results.first as Map;
    final lat = place['latitude'];
    final lon = place['longitude'];
    final weatherReq = await _httpClient!.getUrl(Uri.parse('https://api.open-meteo.com/v1/forecast?latitude=$lat&longitude=$lon&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code&timezone=auto'));
    final weather = await _jsonResponse(await weatherReq.close());
    return jsonEncode({'city': place['name'], 'country': place['country'], 'current': weather['current']});
  }

  Future<String> _executeTool(String name, Map<String, dynamic> args) async {
    switch (name) {
      case 'web_search': return _toolWebSearch(args['query']?.toString() ?? '');
      case 'web_get': return _toolWebGet(args['url']?.toString() ?? '');
      case 'weather': return _toolWeather(args['city']?.toString() ?? '');
      default: throw StateError('Неизвестный Android-инструмент: $name');
    }
  }

  Future<JarvisReply> _sendStandalone(String text) async {
    final local = await _learningCommand(text);
    if (local.text.isNotEmpty) return local;
    final model = await _resolveModel();
    final learning = await _loadLearning();
    final memoryBlock = learning.isEmpty ? 'Сохранённых пользовательских правил нет.' : 'Сохранённые правила:\n${learning.map((x) => '- $x').join('\n')}';
    final messages = <Map<String, dynamic>>[
      {'role': 'system', 'content': 'Ты БУСЯ — самостоятельный AI-агент на Android. Отвечай на языке пользователя. Ты можешь в реальном времени использовать интернет через доступные инструменты. Не утверждай, что выполнила действие, если инструмент его не выполнил. Самоулучшение на Android означает постоянное сохранение и применение пользовательских правил/настроек; не заявляй об изменении весов модели или подписанного APK. $memoryBlock'},
      ..._history.map((m) => Map<String, dynamic>.from(m)),
      {'role': 'user', 'content': text},
    ];
    String? lastTool;
    for (var round = 0; round < 6; round++) {
      final request = await _httpClient!.postUrl(Uri.parse('$_apiUrl/chat/completions'));
      request.headers.contentType = ContentType.json;
      _setAuth(request);
      request.headers.set(HttpHeaders.acceptHeader, 'application/json');
      request.write(jsonEncode({'model': model, 'messages': messages, 'tools': _toolDefinitions(), 'tool_choice': 'auto', 'stream': false}));
      final decoded = await _jsonResponse(await request.close());
      final choices = decoded['choices'];
      if (choices is! List || choices.isEmpty) throw StateError('AI не вернул ответ');
      final message = choices.first['message'];
      if (message is! Map) throw StateError('AI вернул некорректное сообщение');
      final toolCalls = message['tool_calls'];
      final content = message['content'];
      if (toolCalls is List && toolCalls.isNotEmpty) {
        messages.add({'role': 'assistant', 'content': content is String ? content : null, 'tool_calls': toolCalls});
        for (final raw in toolCalls) {
          if (raw is! Map) continue;
          final function = raw['function'];
          if (function is! Map) continue;
          final name = function['name']?.toString() ?? '';
          Map<String, dynamic> args = <String, dynamic>{};
          final rawArgs = function['arguments'];
          if (rawArgs is String && rawArgs.trim().isNotEmpty) {
            final parsed = jsonDecode(rawArgs);
            if (parsed is Map) args = Map<String, dynamic>.from(parsed);
          } else if (rawArgs is Map) args = Map<String, dynamic>.from(rawArgs);
          String result;
          try { result = await _executeTool(name, args); } catch (e) { result = 'Ошибка инструмента $name: $e'; }
          lastTool = name;
          messages.add({'role': 'tool', 'tool_call_id': raw['id']?.toString() ?? name, 'content': result});
        }
        continue;
      }
      if (content is! String || content.trim().isEmpty) throw StateError('AI вернул пустой ответ');
      _history
        ..add({'role': 'user', 'content': text})
        ..add({'role': 'assistant', 'content': content});
      if (_history.length > 40) _history.removeRange(0, _history.length - 40);
      return JarvisReply(content, 'android-agent', lastTool, false);
    }
    throw StateError('AI не завершил цепочку инструментов');
  }

  Future<JarvisReply> sendMessage(String text) async {
    final normalized = text.trim();
    if (normalized.isEmpty) throw ArgumentError('Пустое сообщение');
    if (_standalone) return _sendStandalone(normalized);
    final resp = await _request({'type': 'message', 'text': normalized});
    if (resp['type'] == 'error') throw StateError(resp['message'] as String);
    return JarvisReply.fromJson(resp);
  }

  Future<void> clearMemory() async {
    if (_standalone) { _history.clear(); _learning = <String>[]; await _saveLearning(); return; }
    final resp = await _request({'type': 'clear_memory'});
    if (resp['type'] == 'error') throw StateError(resp['message'] as String);
  }

  Future<List<String>> listTools() async {
    if (_standalone) {
      _lastTools = ['web_search', 'web_get', 'weather', 'android_learning'];
      return List<String>.from(_lastTools!);
    }
    final resp = await _request({'type': 'tools'});
    if (resp['type'] == 'error') throw StateError(resp['message'] as String);
    return (resp['tools'] as List).cast<String>();
  }

  Future<void> dispose() async {
    await _deltaController.close();
    _process?.kill();
    _httpClient?.close(force: true);
  }
}

extension _TakeLast<T> on List<T> {
  List<T> takeLast(int count) => length <= count ? List<T>.from(this) : sublist(length - count);
}
