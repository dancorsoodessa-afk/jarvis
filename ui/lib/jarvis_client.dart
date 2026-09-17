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
      ..idleTimeout = const Duration(seconds: 45);
    return JarvisIpc._(
      httpClient: client,
      apiUrl: normalized,
      apiKey: normalizedKey,
      model: model.trim(),
    );
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

  void _write(Map<String, dynamic> body) {
    _process!.stdin.writeln(jsonEncode(body));
  }

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
      final detail = message == null || message.isEmpty ? 'HTTP ${response.statusCode}' : message;
      throw StateError('AI ${response.statusCode}: $detail');
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
        if (item is Map && item['id'] is String && (item['id'] as String).trim().isNotEmpty) {
          return (item['id'] as String).trim();
        }
      }
    }
    throw StateError('AI-сервер не сообщил доступных моделей. Укажите модель вручную.');
  }

  Future<List<String>> _loadLearning() async {
    if (_learning != null) return List<String>.from(_learning!);
    if (!Platform.isAndroid) {
      _learning = <String>[];
      return <String>[];
    }
    try {
      final raw = await _memoryChannel.invokeMethod<dynamic>('load_learning');
      if (raw is List) {
        _learning = raw.map((e) => e.toString()).where((e) => e.trim().isNotEmpty).toList();
      } else {
        _learning = <String>[];
      }
    } catch (_) {
      _learning = <String>[];
    }
    return List<String>.from(_learning!);
  }

  Future<void> _saveLearning() async {
    if (!Platform.isAndroid || _learning == null) return;
    try {
      await _memoryChannel.invokeMethod('save_learning', {'items': _learning});
    } catch (_) {}
  }

  Future<JarvisReply> _learningCommand(String text) async {
    final lower = text.trim().toLowerCase();
    final items = await _loadLearning();

    const rememberPrefixes = ['запомни ', 'запомни:', 'научись:'];
    for (final prefix in rememberPrefixes) {
      if (lower.startsWith(prefix)) {
        final lesson = text.trim().substring(prefix.length).trim();
        if (lesson.isEmpty) return JarvisReply('Нечего запоминать.', 'local-learning', null, false);
        if (!items.any((x) => x.toLowerCase() == lesson.toLowerCase())) items.add(lesson);
        _learning = items.takeLast(100).toList();
        await _saveLearning();
        return JarvisReply('Запомнила. Сохранено: ${_learning!.length}.', 'local-learning', null, false);
      }
    }

    if (lower == 'что ты запомнила' || lower == 'что ты помнишь' || lower == 'чему ты научилась' || lower == 'покажи память') {
      if (items.isEmpty) return JarvisReply('Пока ничего не сохранено.', 'local-learning', null, false);
      return JarvisReply('Я запомнила:\n${items.asMap().entries.map((e) => '${e.key + 1}. ${e.value}').join('\n')}', 'local-learning', null, false);
    }

    const forgetPrefixes = ['забудь ', 'забудь:'];
    for (final prefix in forgetPrefixes) {
      if (lower.startsWith(prefix)) {
        final target = text.trim().substring(prefix.length).trim().toLowerCase();
        final before = items.length;
        items.removeWhere((x) => x.toLowerCase().contains(target));
        _learning = items;
        await _saveLearning();
        return JarvisReply(before == items.length ? 'Такого правила в памяти не было.' : 'Забыла указанное правило.', 'local-learning', null, false);
      }
    }
    return JarvisReply('', 'none', null, false);
  }

  Future<JarvisReply> _sendStandalone(String text) async {
    final local = await _learningCommand(text);
    if (local.text.isNotEmpty) return local;

    final model = await _resolveModel();
    final learning = await _loadLearning();
    final memoryBlock = learning.isEmpty
        ? 'Сохранённых пользовательских правил нет.'
        : 'Сохранённые пользовательские правила:\n${learning.map((x) => '- $x').join('\n')}';
    final historyForRequest = <Map<String, String>>[
      {
        'role': 'system',
        'content': 'Ты БУСЯ — самостоятельный AI-помощник. Отвечай на языке пользователя. Будь точной, краткой и полезной. Не утверждай, что выполняла действия на устройстве, если у тебя нет соответствующего инструмента. $memoryBlock\nСамоулучшение означает только сохранение и использование пользовательских правил и предложений. Не заявляй, что изменяла веса модели или исходный код.',
      },
      ..._history,
      {'role': 'user', 'content': text},
    ];
    final request = await _httpClient!.postUrl(Uri.parse('$_apiUrl/chat/completions'));
    request.headers.contentType = ContentType.json;
    _setAuth(request);
    request.headers.set(HttpHeaders.acceptHeader, 'application/json');
    request.write(jsonEncode({'model': model, 'messages': historyForRequest, 'stream': false}));
    final decoded = await _jsonResponse(await request.close());
    final choices = decoded['choices'];
    if (choices is! List || choices.isEmpty) throw StateError('AI не вернул ответ');
    final message = choices.first['message'];
    final content = message is Map ? message['content'] : null;
    if (content is! String || content.trim().isEmpty) throw StateError('AI вернул пустой ответ');
    _history
      ..add({'role': 'user', 'content': text})
      ..add({'role': 'assistant', 'content': content});
    if (_history.length > 40) _history.removeRange(0, _history.length - 40);
    return JarvisReply(content, 'standalone-ai', null, false);
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
    if (_standalone) {
      _history.clear();
      _learning = <String>[];
      await _saveLearning();
      return;
    }
    final resp = await _request({'type': 'clear_memory'});
    if (resp['type'] == 'error') throw StateError(resp['message'] as String);
  }

  Future<List<String>> listTools() async {
    if (_standalone) return const [];
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
