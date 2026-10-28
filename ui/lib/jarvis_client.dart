import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

class JarvisReply {
  JarvisReply(this.text, this.provider, this.toolUsed, this.needsConfirmation);
  factory JarvisReply.fromJson(Map<String, dynamic> j) => JarvisReply(
    j['text'] as String, j['provider'] as String? ?? 'unknown',
    j['tool_used'] as String?, j['needs_confirmation'] as bool? ?? false);
  final String text;
  final String provider;
  final String? toolUsed;
  final bool needsConfirmation;
}

class JarvisIpc {
  JarvisIpc._({Process? process, HttpClient? client, String? url, String? key, String? model,
      String? fallbackUrl, String? fallbackKey, String? fallbackModel})
      : _process = process, _httpClient = client, _apiUrl = url, _apiKey = key, _model = model,
        _fallbackUrl = fallbackUrl, _fallbackKey = fallbackKey, _fallbackModel = fallbackModel;

  static String _normalize(String value) {
    var v = value.trim().replaceFirst(RegExp(r'/+$'), '');
    if (v.endsWith('/chat/completions')) v = v.substring(0, v.length - 17);
    return v;
  }

  static Future<JarvisIpc> spawn(String executable, [List<String> args = const ['--ipc']]) async =>
      JarvisIpc._(process: await Process.start(executable, args));

  static Future<JarvisIpc> connectAi(String apiUrl, {String model = '', String apiKey = '',
      String fallbackUrl = '', String fallbackKey = '', String fallbackModel = ''}) async {
    final url = _normalize(apiUrl);
    if (url.isEmpty) throw ArgumentError('AI URL не указан');
    if (apiKey.trim().isEmpty) throw ArgumentError('API key не указан');
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 15)
      ..idleTimeout = const Duration(seconds: 90);
    return JarvisIpc._(client: client, url: url, key: apiKey.trim(), model: model.trim(),
      fallbackUrl: _normalize(fallbackUrl), fallbackKey: fallbackKey.trim(), fallbackModel: fallbackModel.trim());
  }

  final Process? _process;
  final HttpClient? _httpClient;
  final String? _apiUrl;
  final String? _apiKey;
  final String? _model;
  final String? _fallbackUrl;
  final String? _fallbackKey;
  final String? _fallbackModel;
  bool _listening = false;
  StreamSubscription<String>? _stdoutSub;
  StreamSubscription<String>? _stderrSub;
  int _nextId = 0;
  int? _activeId;
  final Map<int, Completer<Map<String, dynamic>>> _pending = {};
  final _deltaController = StreamController<Map<int, String>>.broadcast();
  final List<Map<String, String>> _history = [];
  final Map<String, String> _modelCache = {};
  static const int _maxResponseBytes = 1024 * 1024;
  static const Duration _requestTimeout = Duration(seconds: 45);

  Future<String> _readBody(HttpClientResponse response) async {
    final bytes = BytesBuilder(copy: false);
    await for (final chunk in response) {
      if (bytes.length + chunk.length > _maxResponseBytes) {
        throw StateError('Ответ AI превышает допустимый размер 1 МБ');
      }
      bytes.add(chunk);
    }
    return utf8.decode(bytes.takeBytes());
  }

  Future<String> _resolveModel(String base, String key, String configured) async {
    if (configured.trim().isNotEmpty) return configured.trim();
    final cached = _modelCache[base];
    if (cached != null) return cached;
    final selected = await _autoModel(base, key);
    _modelCache[base] = selected;
    return selected;
  }

  bool get _standalone => _httpClient != null;
  Stream<Map<int, String>> get deltas => _deltaController.stream;
  int? get activeId => _activeId;
  Stream<String> partials() => deltas.map((m) => m[activeId]).where((v) => v != null).cast<String>();

  Map<String, String> _headers(String key) => {
    'Authorization': 'Bearer ${key.trim()}',
    HttpHeaders.acceptHeader: 'application/json',
    HttpHeaders.contentTypeHeader: 'application/json; charset=utf-8',
  };

  String _error(int code, String body) {
    try {
      final j = jsonDecode(body);
      if (j is Map) {
        final e = j['error'];
        if (e is Map && (e['message']?.toString().trim().isNotEmpty ?? false)) return 'HTTP $code: ${e['message'].toString().trim()}';
        if (j['message']?.toString().trim().isNotEmpty ?? false) return 'HTTP $code: ${j['message'].toString().trim()}';
      }
    } catch (_) {}
    final detail = body.trim().isEmpty ? 'пустой ответ сервера' : body.trim();
    return 'HTTP $code: ${detail.length > 500 ? '${detail.substring(0, 500)}…' : detail}';
  }

  Future<String> _autoModel(String base, String key) async {
    final request = await _httpClient!.getUrl(Uri.parse('$base/models'));
    final h = _headers(key)..remove(HttpHeaders.contentTypeHeader);
    h.forEach(request.headers.set);
    final response = await request.close().timeout(const Duration(seconds: 45));
    final body = await _readBody(response).timeout(_requestTimeout);
    if (response.statusCode < 200 || response.statusCode >= 300) throw StateError(_error(response.statusCode, body));
    final j = jsonDecode(body);
    if (j is Map && j['data'] is List) {
      for (final item in j['data']) {
        if (item is Map && item['id'] is String && item['id'].toString().trim().isNotEmpty) return item['id'].toString().trim();
      }
    }
    throw StateError('AI-сервер не сообщил доступных моделей');
  }

  Future<void> _probeChat(String base, String key, String model, String label) async {
    final selected = await _resolveModel(base, key, model);
    final request = await _httpClient!.postUrl(Uri.parse('$base/chat/completions'));
    _headers(key).forEach(request.headers.set);
    final bytes = utf8.encode(jsonEncode({
      'model': selected,
      'messages': [
        {'role': 'user', 'content': 'Ответь только одним словом: OK'}
      ],
      'stream': false,
      'max_tokens': 8,
    }));
    request.contentLength = bytes.length;
    request.add(bytes);
    final response = await request.close().timeout(const Duration(seconds: 45));
    final body = await _readBody(response).timeout(_requestTimeout);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw StateError('$label: ${_error(response.statusCode, body)}');
    }
    try {
      final json = jsonDecode(body);
      final choices = json is Map ? json['choices'] : null;
      final message = choices is List && choices.isNotEmpty ? choices.first['message'] : null;
      final text = message is Map ? message['content']?.toString().trim() : null;
      if (text == null || text.isEmpty) throw StateError('$label: AI вернул пустой ответ');
    } on FormatException {
      throw StateError('$label: сервер вернул некорректный JSON');
    }
  }

  Future<void> checkConnection() async {
    if (!_standalone) return;
    // Validate the actual chat endpoint; /models alone does not prove that
    // the configured model can answer, and HTTP errors must never be ignored.
    try {
      await _probeChat(_apiUrl!, _apiKey!, _model ?? '', 'Основной AI');
      return;
    } catch (primary) {
      if ((_fallbackUrl ?? '').isNotEmpty && (_fallbackKey ?? '').isNotEmpty) {
        try {
          await _probeChat(_fallbackUrl!, _fallbackKey!, _fallbackModel ?? '', 'Резервный AI');
          return;
        } catch (fallback) {
          throw StateError('Основной AI недоступен: $primary. Резервный AI недоступен: $fallback');
        }
      }
      rethrow;
    }
  }

  void _failPending(Object error) {
    for (final entry in _pending.entries) {
      if (!entry.value.isCompleted) entry.value.completeError(error);
    }
    _pending.clear();
  }

  void _ensureListening() {
    if (_standalone || _listening) return;
    _listening = true;
    final process = _process!;
    final lines = process.stdout.transform(utf8.decoder).transform(const LineSplitter());
    final accumulated = <int, String>{};
    _stdoutSub = lines.listen((line) {
      if (line.trim().isEmpty) return;
      try {
        final decoded = jsonDecode(line);
        if (decoded is! Map<String, dynamic>) {
          throw const FormatException('IPC ответ должен быть JSON-объектом');
        }
        final msg = decoded;
        final id = msg['id'] is int ? msg['id'] as int : null;
        if (msg['type'] == 'delta' && id != null) {
          final delta = msg['text'];
          if (delta is! String) throw const FormatException('IPC delta должен содержать текст');
          accumulated[id] = (accumulated[id] ?? '') + delta;
          _deltaController.add({id: accumulated[id]!});
        } else if (id != null) {
          _pending.remove(id)?.complete(msg);
        }
      } catch (error) {
        // A malformed line must not terminate the listener or strand callers.
        _failPending(StateError('Некорректный ответ IPC: $error'));
      }
    }, onError: (Object error, StackTrace stack) {
      _failPending(StateError('Ошибка чтения IPC: $error'));
    }, onDone: () {
      _failPending(StateError('Процесс JARVIS завершил вывод'));
    });
    // Always drain stderr: otherwise a verbose child process can block on a full pipe.
    _stderrSub = process.stderr.transform(utf8.decoder).listen((_) {},
        onError: (Object _) {});
    process.exitCode.then((code) {
      _failPending(StateError('Процесс JARVIS завершился с кодом $code'));
    }).catchError((Object _) {});
  }

  Future<Map<String, dynamic>> _request(Map<String, dynamic> body) {
    _ensureListening();
    final id = _nextId++;
    _activeId = id;
    final c = Completer<Map<String, dynamic>>();
    _pending[id] = c;
    try {
      _process!.stdin.writeln(jsonEncode({...body, 'id': id}));
    } catch (e) {
      _pending.remove(id);
      c.completeError(StateError('Не удалось отправить запрос агенту: $e'));
    }
    return c.future.timeout(const Duration(seconds: 60), onTimeout: () {
      _pending.remove(id);
      throw TimeoutException('Агент не ответил за 60 секунд');
    });
  }

  Future<JarvisReply> _call(String base, String key, String model, String text) async {
    final selected = await _resolveModel(base, key, model);
    final messages = <Map<String, String>>[
      {'role': 'system', 'content': 'Ты JARVIS — AI-помощник. Отвечай на языке пользователя. Не утверждай, что выполнил действие на телефоне, если оно не было выполнено инструментом.'},
      ..._history,
      {'role': 'user', 'content': text},
    ];
    final bytes = utf8.encode(jsonEncode({'model': selected, 'messages': messages, 'stream': false}));
    late HttpClientResponse response;
    late String body;
    // Gemini and other cloud providers can return transient 503/5xx responses.
    // Retry with bounded exponential backoff before handing control to fallback.
    for (var attempt = 0; ; attempt++) {
      final request = await _httpClient!.postUrl(Uri.parse('$base/chat/completions'));
      _headers(key).forEach(request.headers.set);
      request.contentLength = bytes.length;
      request.add(bytes);
      response = await request.close().timeout(const Duration(seconds: 45));
      body = await _readBody(response).timeout(_requestTimeout);
      final retryable = response.statusCode == 429 ||
          response.statusCode == 500 || response.statusCode == 502 ||
          response.statusCode == 503 || response.statusCode == 504;
      if (!retryable || attempt >= 2) break;
      await Future<void>.delayed(Duration(milliseconds: 700 * (1 << attempt)));
    }
    if (response.statusCode < 200 || response.statusCode >= 300) throw StateError(_error(response.statusCode, body));
    final j = jsonDecode(body) as Map<String, dynamic>;
    final choices = j['choices'];
    if (choices is! List || choices.isEmpty) throw StateError('AI не вернул ответ');
    final message = choices.first['message'];
    final content = message is Map ? message['content']?.toString() : null;
    if (content == null || content.trim().isEmpty) throw StateError('AI вернул пустой ответ');
    return JarvisReply(content.trim(), base, null, false);
  }

  Future<JarvisReply> _sendStandalone(String text) async {
    try {
      final r = await _call(_apiUrl!, _apiKey!, _model ?? '', text);
      _history..add({'role': 'user', 'content': text})..add({'role': 'assistant', 'content': r.text});
      if (_history.length > 40) _history.removeRange(0, _history.length - 40);
      return r;
    } catch (primary) {
      if ((_fallbackUrl ?? '').isEmpty || (_fallbackKey ?? '').isEmpty) rethrow;
      try {
        final r = await _call(_fallbackUrl!, _fallbackKey!, _fallbackModel ?? '', text);
        _history..add({'role': 'user', 'content': text})..add({'role': 'assistant', 'content': r.text});
        if (_history.length > 40) _history.removeRange(0, _history.length - 40);
        return r;
      } catch (fallback) {
        throw StateError('Основной AI недоступен: $primary. Резервный AI недоступен: $fallback');
      }
    }
  }

  Future<JarvisReply> sendMessage(String text) async {
    final value = text.trim();
    if (value.isEmpty) throw ArgumentError('Пустое сообщение');
    if (_standalone) return _sendStandalone(value);
    final resp = await _request({'type': 'message', 'text': value});
    if (resp['type'] == 'error') throw StateError(resp['message']?.toString() ?? 'Ошибка агента');
    return JarvisReply.fromJson(resp);
  }

  Future<List<String>> listTools() async {
    if (_standalone) return const [];
    final resp = await _request({'type': 'tools'});
    if (resp['type'] == 'error') throw StateError(resp['message']?.toString() ?? 'Ошибка');
    return (resp['tools'] as List).cast<String>();
  }

  Future<void> dispose() async {
    await _stdoutSub?.cancel();
    await _stderrSub?.cancel();
    _failPending(StateError('JARVIS IPC остановлен'));
    await _deltaController.close();
    _process?.kill();
    _httpClient?.close(force: true);
  }
}
