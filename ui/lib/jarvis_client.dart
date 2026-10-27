import 'dart:async';
import 'dart:convert';
import 'dart:io';

class JarvisReply {
  JarvisReply(this.text, this.provider, this.toolUsed, this.needsConfirmation);
  factory JarvisReply.fromJson(Map<String, dynamic> j) => JarvisReply(
    j['text'] as String,
    j['provider'] as String? ?? 'unknown',
    j['tool_used'] as String?,
    j['needs_confirmation'] as bool? ?? false,
  );
  final String text;
  final String provider;
  final String? toolUsed;
  final bool needsConfirmation;
}

class JarvisIpc {
  JarvisIpc._({
    Process? process,
    HttpClient? client,
    String? url,
    String? key,
    String? model,
    String? fallbackUrl,
    String? fallbackKey,
    String? fallbackModel,
  }) : _process = process,
       _httpClient = client,
       _apiUrl = url,
       _apiKey = key,
       _model = model,
       _fallbackUrl = fallbackUrl,
       _fallbackKey = fallbackKey,
       _fallbackModel = fallbackModel;

  static String _normalize(String value) {
    var v = value.trim().replaceFirst(RegExp(r'/+$'), '');
    if (v.endsWith('/chat/completions')) {
      v = v.substring(0, v.length - 17);
    }
    return v;
  }

  static Future<JarvisIpc> spawn(
    String executable, [
    List<String> args = const ['--ipc'],
  ]) async => JarvisIpc._(process: await Process.start(executable, args));

  static Future<JarvisIpc> connectAi(
    String apiUrl, {
    String model = '',
    String apiKey = '',
    String fallbackUrl = '',
    String fallbackKey = '',
    String fallbackModel = '',
  }) async {
    final url = _normalize(apiUrl);
    if (url.isEmpty) throw ArgumentError('AI URL не указан');
    if (apiKey.trim().isEmpty) throw ArgumentError('API key не указан');

    final client = HttpClient();
    client.connectionTimeout = const Duration(seconds: 15);
    client.idleTimeout = const Duration(seconds: 30);
    // Use Android's normal resolver and TLS/socket handling. The previous
    // custom DNS-over-HTTPS socket factory bypassed platform networking and
    // could abort otherwise valid HTTPS requests on mobile networks.

    return JarvisIpc._(
      client: client,
      url: url,
      key: apiKey.trim(),
      model: model.trim(),
      fallbackUrl: _normalize(fallbackUrl),
      fallbackKey: fallbackKey.trim(),
      fallbackModel: fallbackModel.trim(),
    );
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
  int _nextId = 0;
  int? _activeId;
  final Map<int, Completer<Map<String, dynamic>>> _pending = {};
  final _deltaController = StreamController<Map<int, String>>.broadcast();
  final List<Map<String, String>> _history = [];

  bool get _standalone => _httpClient != null;
  Stream<Map<int, String>> get deltas => _deltaController.stream;
  int? get activeId => _activeId;
  Stream<String> partials() =>
      deltas.map((m) => m[activeId]).where((v) => v != null).cast<String>();

  Map<String, String> _headers(String key) => {
    'Authorization': 'Bearer ${key.trim()}',
    HttpHeaders.acceptHeader: 'application/json',
    HttpHeaders.contentTypeHeader: 'application/json; charset=utf-8',
  };

  String _networkError(Object error, String base) {
    final s = error.toString();
    if (s.contains('Failed host lookup') ||
        s.contains('No address associated with hostname')) {
      try {
        Uri.parse(base).host;
        return 'Сеть: системный DNS недоступен. проверьте интернет, системный DNS/VPN или используйте резервный AI.';
      } catch (_) {
        return 'Сеть: не удалось найти сервер AI через DNS. Проверьте интернет/VPN/DNS или используйте резервный AI.';
      }
    }
    if (s.contains('SocketException')) {
      return 'Сеть: не удалось соединиться с AI-сервером. Проверьте интернет/VPN или резервный AI.';
    }
    if (s.contains('TimeoutException')) {
      return 'Сеть: истекло время ожидания AI-сервера. Проверьте интернет/VPN или резервный AI.';
    }
    return s;
  }

  String _error(int code, String body) {
    if (code == 429) {
      String detail = '';
      try {
        final j = jsonDecode(body);
        if (j is Map) {
          final e = j['error'];
          if (e is Map) detail = e['message']?.toString() ?? '';
          if (detail.isEmpty) detail = j['message']?.toString() ?? '';
        }
      } catch (_) {}
      final quota = RegExp(r'quota|rate.?limit|resource.?exhausted|billing|limit', caseSensitive: false).hasMatch('$detail $body');
      return quota
          ? 'HTTP 429: Google Gemini ограничил запросы или исчерпана квота. Проверь лимиты/биллинг в Google AI Studio и подожди сброса квоты. JARVIS не будет повторять этот запрос автоматически.'
          : 'HTTP 429: слишком много запросов к AI. Подожди немного и повтори один раз вручную.';
    }
    try {
      final j = jsonDecode(body);
      if (j is Map) {
        final e = j['error'];
        if (e is Map &&
            (e['message']?.toString().trim().isNotEmpty ?? false)) {
          return 'HTTP $code: ${e['message'].toString().trim()}';
        }
        if (j['message']?.toString().trim().isNotEmpty ?? false) {
          return 'HTTP $code: ${j['message'].toString().trim()}';
        }
      }
    } catch (_) {}
    return 'HTTP $code: ${body.trim().isEmpty ? 'пустой ответ сервера' : body.trim()}';
  }

  Future<T> _retryTransient<T>(Future<T> Function() action) async {
    for (var attempt = 0; ; attempt++) {
      try {
        return await action();
      } catch (e) {
        final transient = RegExp(r'HTTP (408|500|502|503|504)').hasMatch(e.toString()) ||
            e is SocketException || e is TimeoutException ||
            e.toString().contains('Connection closed');
        if (!transient || attempt >= 1) rethrow;
        await Future.delayed(Duration(seconds: 1 << attempt));
      }
    }
  }

  Future<String> _autoModel(String base, String key) async {
    final request = await _httpClient!.getUrl(Uri.parse('$base/models'));
    final h = _headers(key)..remove(HttpHeaders.contentTypeHeader);
    h.forEach(request.headers.set);
    final response = await request.close();
    final body = await utf8.decoder.bind(response).join();
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw StateError(_error(response.statusCode, body));
    }
    final j = jsonDecode(body);
    if (j is Map && j['data'] is List) {
      for (final item in j['data']) {
        if (item is Map &&
            item['id'] is String &&
            item['id'].toString().trim().isNotEmpty) {
          return item['id'].toString().trim();
        }
      }
    }
    throw StateError('AI-сервер не сообщил доступных моделей');
  }

  Future<void> checkConnection() async {
    if (!_standalone) return;
    // Do not probe GET /models: Google's OpenAI-compatible endpoint may reject
    // model-list requests even when chat completions are supported. Verify by
    // making a tiny real completion against the selected model instead.
    final primaryModel = (_model ?? '').trim().isEmpty
        ? 'gemini-3.8-flash'
        : _model!.trim();
    try {
      await _call(_apiUrl!, _apiKey!, primaryModel,
          'Ответь одним словом: готов.');
    } catch (e) {
      // If the primary Gemini model is throttled or unavailable, verify the
      // same key/endpoint against the lighter stable fallback model.
      final isGemini = (_apiUrl ?? '').contains('generativelanguage.googleapis.com/v1beta/openai');
      if (isGemini && primaryModel != 'gemini-3.5-flash-lite') {
        try {
          await _call(_apiUrl!, _apiKey!, 'gemini-3.5-flash-lite',
              'Ответь одним словом: готов.');
          return;
        } catch (_) {
          // Continue to the explicitly configured provider fallback below.
        }
      }
      if ((_fallbackUrl ?? '').isNotEmpty && (_fallbackKey ?? '').isNotEmpty) {
        final fallbackModel = (_fallbackModel ?? '').trim().isEmpty
            ? ''
            : _fallbackModel!.trim();
        await _call(_fallbackUrl!, _fallbackKey!, fallbackModel,
            'Ответь одним словом: готов.');
      } else {
        rethrow;
      }
    }
  }

  void _ensureListening() {
    if (_standalone || _listening) return;
    _listening = true;
    final lines = _process!.stdout.transform(utf8.decoder).transform(const LineSplitter());
    final accumulated = <int, String>{};
    lines.listen((line) {
      if (line.trim().isEmpty) return;
      final msg = jsonDecode(line) as Map<String, dynamic>;
      final id = msg['id'] is int ? msg['id'] as int : null;
      if (msg['type'] == 'delta' && id != null) {
        accumulated[id] = (accumulated[id] ?? '') + (msg['text'] as String);
        _deltaController.add({id: accumulated[id]!});
      } else if (id != null) {
        _pending.remove(id)?.complete(msg);
      }
    });
  }

  Future<Map<String, dynamic>> _request(Map<String, dynamic> body) {
    _ensureListening();
    final id = _nextId++;
    _activeId = id;
    final c = Completer<Map<String, dynamic>>();
    _pending[id] = c;
    _process!.stdin.writeln(jsonEncode({...body, 'id': id}));
    return c.future;
  }

  Future<JarvisReply> _call(
    String base,
    String key,
    String model,
    String text,
  ) async {
    final selected = model.trim().isEmpty
        ? (base.contains('generativelanguage.googleapis.com/v1beta/openai')
            ? 'gemini-3.8-flash'
            : await _autoModel(base, key))
        : model.trim();
    final messages = <Map<String, String>>[
      {
        'role': 'system',
        'content':
            'Ты JARVIS — AI-помощник. Отвечай на языке пользователя. Не утверждай, что выполнил действие на телефоне, если оно не было выполнено инструментом.',
      },
      ..._history,
      {'role': 'user', 'content': text},
    ];
    return _retryTransient(() async {
      final request = await _httpClient!.postUrl(Uri.parse('$base/chat/completions')).timeout(const Duration(seconds: 20));
      _headers(key).forEach(request.headers.set);
      final bytes = utf8.encode(
        jsonEncode({'model': selected, 'messages': messages, 'stream': false}),
      );
      request.contentLength = bytes.length;
      request.add(bytes);
      final response = await request.close().timeout(const Duration(seconds: 25));
      final body = await utf8.decoder.bind(response).join().timeout(const Duration(seconds: 25));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw StateError(_error(response.statusCode, body));
      }
      final j = jsonDecode(body) as Map<String, dynamic>;
      final choices = j['choices'];
      if (choices is! List || choices.isEmpty) {
        throw StateError('AI не вернул ответ');
      }
      final message = choices.first['message'];
      final content = message is Map ? message['content']?.toString() : null;
      if (content == null || content.trim().isEmpty) {
        throw StateError('AI вернул пустой ответ');
      }
      return JarvisReply(content.trim(), base, null, false);
    });
  }

  bool _retryable(Object e) {
    final s = e.toString();
    return RegExp(
          r'HTTP (400|401|402|403|404|408|409|425|500|502|503|504)',
        ).hasMatch(s) ||
        s.contains('SocketException') ||
        s.contains('TimeoutException') ||
        s.contains('Connection closed');
  }

  Future<JarvisReply> _sendStandalone(String text) async {
    try {
      final r = await _call(_apiUrl!, _apiKey!, _model ?? '', text);
      _history
        ..add({'role': 'user', 'content': text})
        ..add({'role': 'assistant', 'content': r.text});
      if (_history.length > 40) {
        _history.removeRange(0, _history.length - 40);
      }
      return r;
    } catch (e) {
      final errorText = e.toString();
      final isGemini = (_apiUrl ?? '').contains('generativelanguage.googleapis.com/v1beta/openai');
      final primaryModel = (_model ?? '').trim().isEmpty ? 'gemini-3.8-flash' : _model!.trim();
      final quotaOrModelError = RegExp(r'HTTP (400|403|404|429)').hasMatch(errorText);
      if (isGemini && primaryModel != 'gemini-3.5-flash-lite' &&
          (quotaOrModelError || _retryable(e))) {
        try {
          final r = await _call(_apiUrl!, _apiKey!, 'gemini-3.5-flash-lite', text);
          _history
            ..add({'role': 'user', 'content': text})
            ..add({'role': 'assistant', 'content': r.text});
          if (_history.length > 40) {
            _history.removeRange(0, _history.length - 40);
          }
          return JarvisReply(r.text, 'Gemini Flash-Lite (резерв)', r.toolUsed, r.needsConfirmation);
        } catch (_) {
          // If the lighter Gemini model is also unavailable, try configured
          // secondary provider below, otherwise report the original error.
        }
      }
      if ((_fallbackUrl ?? '').isEmpty ||
          (_fallbackKey ?? '').isEmpty ||
          (!_retryable(e) && !quotaOrModelError)) {
        if (e is SocketException ||
            e.toString().contains('Failed host lookup') ||
            e.toString().contains('TimeoutException')) {
          throw StateError(_networkError(e, _apiUrl!));
        }
        rethrow;
      }
      try {
        final r = await _call(
          _fallbackUrl!,
          _fallbackKey!,
          _fallbackModel ?? '',
          text,
        );
        _history
          ..add({'role': 'user', 'content': text})
          ..add({'role': 'assistant', 'content': r.text});
        if (_history.length > 40) {
          _history.removeRange(0, _history.length - 40);
        }
        return r;
      } catch (fallbackError) {
        if (fallbackError is SocketException ||
            fallbackError.toString().contains('Failed host lookup') ||
            fallbackError.toString().contains('TimeoutException')) {
          throw StateError(
            'Основной и резервный AI недоступны по сети. ' +
                _networkError(fallbackError, _fallbackUrl!),
          );
        }
        rethrow;
      }
    }
  }

  Future<JarvisReply> sendMessage(String text) async {
    final value = text.trim();
    if (value.isEmpty) throw ArgumentError('Пустое сообщение');
    if (_standalone) return _sendStandalone(value);
    final resp = await _request({'type': 'message', 'text': value});
    if (resp['type'] == 'error') {
      throw StateError(resp['message']?.toString() ?? 'Ошибка агента');
    }
    return JarvisReply.fromJson(resp);
  }

  Future<List<String>> listTools() async {
    if (_standalone) return const [];
    final resp = await _request({'type': 'tools'});
    if (resp['type'] == 'error') {
      throw StateError(resp['message']?.toString() ?? 'Ошибка');
    }
    return (resp['tools'] as List).cast<String>();
  }

  Future<void> dispose() async {
    await _deltaController.close();
    _process?.kill();
    _httpClient?.close(force: true);
  }
}

