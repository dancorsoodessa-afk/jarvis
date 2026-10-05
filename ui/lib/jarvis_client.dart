import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

class _DnsResolver {
  static const _servers = ['1.1.1.1', '8.8.8.8'];
  static final Map<String, List<InternetAddress>> _cache = {};
  static final Map<String, DateTime> _cacheTime = {};

  static Future<List<InternetAddress>> lookup(String host) async {
    final now = DateTime.now();
    final cached = _cache[host];
    final cachedAt = _cacheTime[host];
    if (cached != null && cachedAt != null &&
        now.difference(cachedAt) < const Duration(minutes: 5)) {
      return cached;
    }
    for (final server in _servers) {
      try {
        final result = await _query(server, host);
        if (result.isNotEmpty) {
          _cache[host] = result;
          _cacheTime[host] = now;
          return result;
        }
      } catch (_) {}
    }
    throw SocketException('DNS lookup failed for $host');
  }

  static Future<List<InternetAddress>> _query(String server, String host) async {
    final id = Random().nextInt(0x10000);
    final packet = <int>[
      id >> 8, id & 0xff, 0x01, 0x00, 0x00, 0x01, 0, 0, 0, 0, 0, 0
    ];
    for (final label in host.split('.')) {
      final bytes = utf8.encode(label);
      packet.add(bytes.length);
      packet.addAll(bytes);
    }
    packet.add(0);
    packet.addAll([0, 1, 0, 1]);

    final socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0);
    try {
      socket.send(Uint8List.fromList(packet), InternetAddress(server), 53);
      final completer = Completer<Uint8List>();
      late StreamSubscription<RawSocketEvent> sub;
      Timer? timer;
      sub = socket.listen((event) {
        if (event != RawSocketEvent.read) return;
        final dg = socket.receive();
        if (dg == null || dg.data.length < 12) return;
        final data = Uint8List.fromList(dg.data);
        final responseId = (data[0] << 8) | data[1];
        if (responseId == id && !completer.isCompleted) {
          completer.complete(data);
        }
      });
      timer = Timer(const Duration(seconds: 3), () {
        if (!completer.isCompleted) {
          completer.completeError(TimeoutException('DNS timeout'));
        }
      });
      try {
        final data = await completer.future;
        final answers = <InternetAddress>[];
        final qd = (data[4] << 8) | data[5];
        final an = (data[6] << 8) | data[7];
        var offset = 12;

        int skipName(int at) {
          while (at < data.length) {
            final len = data[at];
            if (len == 0) return at + 1;
            if ((len & 0xc0) == 0xc0) return at + 2;
            at += len + 1;
          }
          return at;
        }

        for (var i = 0; i < qd; i++) {
          offset = skipName(offset) + 4;
        }
        for (var i = 0; i < an && offset + 10 <= data.length; i++) {
          offset = skipName(offset);
          if (offset + 10 > data.length) break;
          final type = (data[offset] << 8) | data[offset + 1];
          final rdLength = (data[offset + 8] << 8) | data[offset + 9];
          offset += 10;
          if (offset + rdLength > data.length) break;
          if (type == 1 && rdLength == 4) {
            answers.add(InternetAddress(
              '${data[offset]}.${data[offset + 1]}.${data[offset + 2]}.${data[offset + 3]}',
            ));
          }
          offset += rdLength;
        }
        return answers;
      } finally {
        timer.cancel();
        await sub.cancel();
      }
    } finally {
      socket.close();
    }
  }
}

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

  static Future<Socket> _connectWithoutSystemDns(Uri uri) async {
    final addresses = await _DnsResolver.lookup(uri.host);
    for (final address in addresses) {
      Socket? socket;
      try {
        socket = await Socket.connect(
          address,
          uri.hasPort ? uri.port : 443,
          timeout: const Duration(seconds: 12),
        );
        if (uri.scheme == 'https') {
          return await SecureSocket.secure(socket, host: uri.host);
        }
        return socket;
      } catch (_) {
        socket?.destroy();
      }
    }
    throw SocketException('Не удалось подключиться к ${uri.host}');
  }

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
    client.idleTimeout = const Duration(seconds: 90);
    client.findProxy = (_) => 'DIRECT';
    client.connectionFactory = (uri, proxyHost, proxyPort) {
      final future = _connectWithoutSystemDns(uri);
      return ConnectionTask.fromSocket(future, () {});
    };

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
    'HTTP-Referer': 'https://github.com/dancorsoodessa-afk/jarvis',
    'X-Title': 'JARVIS Android',
  };

  String _networkError(Object error, String base) {
    final s = error.toString();
    if (s.contains('Failed host lookup') ||
        s.contains('No address associated with hostname')) {
      try {
        Uri.parse(base).host;
        return 'Сеть: системный DNS недоступен. JARVIS использует встроенное DNS-подключение; проверьте наличие интернета.';
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

  Future<void> _check(String base, String key, String label) async {
    final request = await _httpClient!.getUrl(Uri.parse('$base/models'));
    final h = _headers(key)..remove(HttpHeaders.contentTypeHeader);
    h.forEach(request.headers.set);
    final response = await request.close();
    final body = await utf8.decoder.bind(response).join();
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw StateError('$label: ${_error(response.statusCode, body)}');
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
    try {
      await _check(_apiUrl!, _apiKey!, 'Основной AI');
    } catch (e) {
      if ((_fallbackUrl ?? '').isNotEmpty && (_fallbackKey ?? '').isNotEmpty) {
        await _check(_fallbackUrl!, _fallbackKey!, 'Резервный AI');
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
        ? await _autoModel(base, key)
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
    final request =
        await _httpClient!.postUrl(Uri.parse('$base/chat/completions'));
    _headers(key).forEach(request.headers.set);
    final bytes = utf8.encode(
      jsonEncode({'model': selected, 'messages': messages, 'stream': false}),
    );
    request.contentLength = bytes.length;
    request.add(bytes);
    final response = await request.close();
    final body = await utf8.decoder.bind(response).join();
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
  }

  bool _retryable(Object e) {
    final s = e.toString();
    return RegExp(
          r'HTTP (400|401|402|403|404|408|409|425|429|500|502|503|504)',
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
      if ((_fallbackUrl ?? '').isEmpty ||
          (_fallbackKey ?? '').isEmpty ||
          !_retryable(e)) {
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
