import 'dart:async';
import 'dart:convert';
import 'dart:io';

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
    // OrcaRouter and other OpenAI-compatible gateways use Bearer auth.
    // X-API-Key is also sent for gateways that expose the same API under that convention.
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

  Future<JarvisReply> _sendStandalone(String text) async {
    final model = await _resolveModel();
    final historyForRequest = <Map<String, String>>[
      {
        'role': 'system',
        'content': 'Ты JARVIS — самостоятельный AI-помощник. Отвечай на языке пользователя. Будь точным, кратким и полезным. Не утверждай, что выполнял действия на устройстве, если у тебя нет соответствующего инструмента.',
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
