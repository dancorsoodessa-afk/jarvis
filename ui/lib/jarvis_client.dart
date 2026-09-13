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
  JarvisIpc._({Process? process, Socket? socket})
      : _process = process,
        _socket = socket;

  static Future<JarvisIpc> spawn(String executable,
      [List<String> args = const ['--ipc']]) async {
    final process = await Process.start(executable, args);
    return JarvisIpc._(process: process);
  }

  static Future<JarvisIpc> connectTcp(String host, int port) async {
    final socket = await Socket.connect(host, port, timeout: const Duration(seconds: 5));
    return JarvisIpc._(socket: socket);
  }

  final Process? _process;
  final Socket? _socket;
  int _nextId = 0;
  int? _activeId;
  bool _listening = false;
  final Map<int, Completer<Map<String, dynamic>>> _pending = {};
  final _deltaController = StreamController<Map<int, String>>.broadcast();

  Stream<Map<int, String>> get deltas => _deltaController.stream;
  int? get activeId => _activeId;
  Stream<String> partials() => deltas
      .map((m) => m[activeId])
      .where((value) => value != null)
      .cast<String>();

  void _ensureListening() {
    if (_listening) return;
    _listening = true;
    final accumulated = <int, String>{};
    final lines = (_process != null ? _process!.stdout : _socket!)
        .transform(utf8.decoder)
        .transform(const LineSplitter());
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
      for (final c in _pending.values) {
        if (!c.isCompleted) c.completeError(error);
      }
      _pending.clear();
    });
  }

  void _write(Map<String, dynamic> body) {
    final line = jsonEncode(body);
    if (_process != null) {
      _process!.stdin.writeln(line);
    } else {
      _socket!.write('$line\n');
    }
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

  Future<JarvisReply> sendMessage(String text) async {
    final resp = await _request({'type': 'message', 'text': text});
    if (resp['type'] == 'error') throw StateError(resp['message'] as String);
    return JarvisReply.fromJson(resp);
  }

  Future<void> clearMemory() async {
    final resp = await _request({'type': 'clear_memory'});
    if (resp['type'] == 'error') throw StateError(resp['message'] as String);
  }

  Future<List<String>> listTools() async {
    final resp = await _request({'type': 'tools'});
    if (resp['type'] == 'error') throw StateError(resp['message'] as String);
    return (resp['tools'] as List).cast<String>();
  }

  Future<void> dispose() async {
    await _deltaController.close();
    await _socket?.close();
    _process?.kill();
  }
}
