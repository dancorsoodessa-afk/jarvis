import 'dart:async';
import 'dart:convert';
import 'dart:io';

class JarvisReply {
  JarvisReply(this.text, this.provider, this.toolUsed, this.needsConfirmation);
  factory JarvisReply.fromJson(Map<String, dynamic> json) => JarvisReply(
        (json['text'] ?? '').toString(),
        (json['provider'] ?? 'openrouter').toString(),
        json['tool_used'] as String?,
        json['needs_confirmation'] as bool? ?? false,
      );
  final String text;
  final String provider;
  final String? toolUsed;
  final bool needsConfirmation;
}

class JarvisIpc {
  JarvisIpc._(Process process)
      : _process = process,
        _baseUri = null,
        _apiKey = null,
        _model = null;
  JarvisIpc._android(Uri baseUri, String apiKey, String model)
      : _process = null,
        _baseUri = baseUri,
        _apiKey = apiKey,
        _model = model;

  static Future<JarvisIpc> spawn(String executable,
      [List<String> args = const ['--ipc']]) async {
    final process = await Process.start(executable, args);
    return JarvisIpc._(process);
  }

  static Future<JarvisIpc> connectAi(String endpoint,
      {required String apiKey, required String model}) async {
    final raw = endpoint.trim().replaceAll(RegExp(r'/+$'), '');
    final base = raw.endsWith('/chat/completions')
        ? raw.substring(0, raw.length - '/chat/completions'.length)
        : raw;
    final normalized = base.endsWith('/v1') ? base : '$base/v1';
    return JarvisIpc._android(
      Uri.parse(normalized),
      apiKey.trim(),
      model.trim().isEmpty ? 'openrouter/free' : model.trim(),
    );
  }

  final Process? _process;
  final Uri? _baseUri;
  final String? _apiKey;
  final String? _model;

  int _nextId = 0;
  final Map<int, Completer<Map<String, dynamic>>> _pending = {};
  final _deltaController = StreamController<Map<int, String>>.broadcast();
  bool _listening = false;
  int? _activeId;

  Stream<Map<int, String>> get deltas => _deltaController.stream;
  int? get activeId => _activeId;

  void _ensureListening() {
    if (_process == null || _listening) return;
    _listening = true;
    final accumulated = <int, String>{};
    _process!.stdout.transform(utf8.decoder).transform(const LineSplitter()).listen((line) {
      if (line.trim().isEmpty) return;
      try {
        final msg = jsonDecode(line) as Map<String, dynamic>;
        final id = msg['id'] as int?;
        if (msg['type'] == 'delta' && id != null) {
          accumulated[id] = (accumulated[id] ?? '') + (msg['text'] ?? '').toString();
          _deltaController.add({id: accumulated[id]!});
          return;
        }
        final completer = id != null ? _pending.remove(id) : null;
        completer?.complete(msg);
      } catch (_) {}
    });
  }

  Stream<String> partials() => deltas
      .map((m) => m[activeId])
      .where((t) => t != null)
      .cast<String>();

  Future<Map<String, dynamic>> _request(Map<String, dynamic> body) {
    _ensureListening();
    final id = _nextId++;
    _activeId = id;
    final completer = Completer<Map<String, dynamic>>();
    _pending[id] = completer;
    _process!.stdin.writeln(jsonEncode({...body, 'id': id}));
    return completer.future;
  }

  Future<Map<String, dynamic>> _http(String path,
      {String method = 'GET', Map<String, dynamic>? body}) async {
    final base = _baseUri;
    final key = _apiKey;
    if (base == null || key == null || key.isEmpty) {
      throw StateError('AI-клиент не настроен');
    }
    final uri = base.resolve(path.startsWith('/') ? path.substring(1) : path);
    final client = HttpClient();
    try {
      final request = await client.openUrl(method, uri);
      request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $key');
      request.headers.contentType = ContentType.json;
      request.headers.set('HTTP-Referer', 'https://github.com/dancorsoodessa-afk/jarvis');
      request.headers.set('X-Title', 'JARVIS');
      if (body != null) request.add(utf8.encode(jsonEncode(body)));
      final response = await request.close().timeout(const Duration(seconds: 45));
      final text = await response.transform(utf8.decoder).join();
      Map<String, dynamic> data = {};
      if (text.isNotEmpty) {
        try { data = jsonDecode(text) as Map<String, dynamic>; } catch (_) {}
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final message = data['error'] is Map
            ? (data['error']['message'] ?? data['error']).toString()
            : (data['message'] ?? text).toString();
        throw StateError('HTTP ${response.statusCode}: $message');
      }
      return data;
    } finally {
      client.close(force: true);
    }
  }

  Future<void> verifyConnection() async {
    final data = await _http('/models');
    if (data['data'] is! List) {
      throw StateError('OpenRouter не вернул список моделей');
    }
  }

  Future<JarvisReply> sendMessage(String text,
      {Map<String, dynamic>? attachment}) async {
    if (_process != null) {
      final body = <String, dynamic>{'type': 'message', 'text': text};
      if (attachment != null) body['attachment'] = attachment;
      final resp = await _request(body);
      if (resp['type'] == 'error') {
        throw StateError((resp['message'] ?? 'Ошибка агента').toString());
      }
      return JarvisReply.fromJson(resp);
    }

    final content = <dynamic>[{'type': 'text', 'text': text}];
    if (attachment != null && attachment['data'] != null) {
      final mime = (attachment['mime'] ?? 'application/octet-stream').toString();
      content.add({
        'type': 'image_url',
        'image_url': {'url': 'data:$mime;base64:${attachment['data']}'}
      });
    }
    final data = await _http('/chat/completions', method: 'POST', body: {
      'model': _model,
      'messages': [
        {'role': 'system', 'content': 'Ты JARVIS. Отвечай по-русски кратко и по делу.'},
        {'role': 'user', 'content': content.length == 1 ? text : content},
      ],
      'stream': false,
    });
    final choices = data['choices'];
    if (choices is! List || choices.isEmpty) {
      throw StateError('AI не вернул ответ');
    }
    final message = choices.first['message'];
    final raw = message is Map ? message['content'] : null;
    final answer = raw is String ? raw : (raw ?? '').toString();
    if (answer.trim().isEmpty) throw StateError('AI вернул пустой ответ');
    return JarvisReply(answer, 'openrouter', null, false);
  }

  Future<JarvisReply> confirm(String yesOrNo) => sendMessage(yesOrNo);
  Future<void> clearMemory() async {}

  Future<List<String>> listTools() async {
    if (_process != null) {
      final resp = await _request({'type': 'tools'});
      return (resp['tools'] as List).cast<String>();
    }
    return const <String>[];
  }

  Future<void> dispose() async {
    if (_process != null) {
      _process!.kill();
      await _process!.exitCode;
    }
    await _deltaController.close();
  }
}
