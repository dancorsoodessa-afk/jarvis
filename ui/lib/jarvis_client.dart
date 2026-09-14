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
  JarvisIpc._({Process? process, Socket? socket, HttpClient? httpClient, String? apiUrl, String? apiKey, String? model})
      : _process = process, _socket = socket, _httpClient = httpClient, _apiUrl = apiUrl, _apiKey = apiKey, _model = model;

  static Future<JarvisIpc> spawn(String executable, [List<String> args = const ['--ipc']]) async {
    final process = await Process.start(executable, args);
    return JarvisIpc._(process: process);
  }

  static Future<JarvisIpc> connectAi(String apiUrl, {String model = '', String apiKey = ''}) async {
    var normalized = apiUrl.trim().replaceFirst(RegExp(r'/+$'), '');
    if (normalized.endsWith('/chat/completions')) {
      normalized = normalized.substring(0, normalized.length - '/chat/completions'.length);
    }
    if (normalized.isEmpty) throw ArgumentError('AI endpoint не указан');
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 15)
      ..idleTimeout = const Duration(seconds: 30);
    return JarvisIpc._(httpClient: client, apiUrl: normalized, apiKey: apiKey.trim(), model: model.trim());
  }

  final Process? _process;
  final Socket? _socket;
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
    final lines = (_process != null ? _process!.stdout : _socket!).transform(utf8.decoder).transform(const LineSplitter());
    lines.listen((line) {
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
      for (final c in _pending.values) { if (!c.isCompleted) c.completeError(error); }
      _pending.clear();
    });
  }

  void _write(Map<String, dynamic> body) {
    final line = jsonEncode(body);
    if (_process != null) { _process!.stdin.writeln(line); } else { _socket!.write('$line\n'); }
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

  Future<String> _resolveModel() async {
    if (_model != null && _model!.isNotEmpty) return _model!;
    final uri = Uri.parse('$_apiUrl/models');
    final request = await _httpClient!.getUrl(uri);
    request.headers.set(HttpHeaders.acceptHeader, 'application/json');
    if (_apiKey != null && _apiKey!.isNotEmpty) request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $_apiKey');
    final response = await request.close();
    final body = await utf8.decoder.bind(response).join();
    if (response.statusCode < 200 || response.statusCode >= 300) throw StateError('Не удалось получить список AI-моделей: HTTP ${response.statusCode}');
    final decoded = body.isEmpty ? <String, dynamic>{} : jsonDecode(body) as Map<String, dynamic>;
    final data = decoded['data'];
    if (data is List) {
      for (final item in data) {
        if (item is Map && item['id'] is String && (item['id'] as String).trim().isNotEmpty) return (item['id'] as String).trim();
      }
    }
    throw StateError('AI-сервер не сообщил доступных моделей. Укажите модель вручную.');
  }

  Future<JarvisReply> _sendStandalone(String text) async {
    final model = await _resolveModel();
    final historyForRequest = <Map<String, String>>[
      {'role': 'system', 'content': 'Ты JARVIS — самостоятельный AI-помощник. Отвечай на языке пользователя. Будь точным, кратким и полезным. Не утверждай, что выполнял действия на устройстве, если у тебя нет соответствующего инструмента.'},
      ..._history,
      {'role': 'user', 'content': text},
    ];
    final uri = Uri.parse('$_apiUrl/chat/completions');
    final request = await _httpClient!.postUrl(uri);
    request.headers.contentType = ContentType.json;
    if (_apiKey != null && _apiKey!.isNotEmpty) request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $_apiKey');
    request.headers.set('Accept', 'application/json');
    request.write(jsonEncode({'model': model, 'messages': historyForRequest, 'stream': false}));
    final response = await request.close();
    final body = await utf8.decoder.bind(response).join();
    final decoded = body.isEmpty ? <String, dynamic>{} : jsonDecode(body) as Map<String, dynamic>;
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final error = decoded['error'];
      final message = error is Map ? error['message']?.toString() : decoded['message']?.toString();
      throw StateError(message == null || message.isEmpty ? 'AI HTTP ${response.statusCode}' : message);
    }
    final choices = decoded['choices'];
    if (choices is! List || choices.isEmpty) throw StateError('AI не вернул ответ');
    final message = choices.first['message'];
    final content = message is Map ? message['content'] : null;
    if (content is! String || content.trim().isEmpty) throw StateError('AI вернул пустой ответ');
    _history..add({'role': 'user', 'content': text})..add({'role': 'assistant', 'content': content});
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
    if (_standalone) { _history.clear(); return; }
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
    await _socket?.close();
    _process?.kill();
    _httpClient?.close(force: true);
  }
}
