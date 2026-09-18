import 'dart:async';
import 'dart:convert';
import 'dart:io';

class JarvisReply {
  JarvisReply(this.text, this.provider, this.toolUsed, this.needsConfirmation);
  factory JarvisReply.fromJson(Map<String, dynamic> json) => JarvisReply(
        json['text'] as String,
        json['provider'] as String,
        json['tool_used'] as String?,
        json['needs_confirmation'] as bool? ?? false,
      );
  final String text;
  final String provider;
  final String? toolUsed;
  final bool needsConfirmation;
}

class JarvisIpc {
  JarvisIpc._(this._process);
  static Future<JarvisIpc> spawn(String executable,
      [List<String> args = const ['--ipc']]) async {
    final process = await Process.start(executable, args);
    return JarvisIpc._(process);
  }

  final Process _process;
  int _nextId = 0;
  final Map<int, Completer<Map<String, dynamic>>> _pending = {};
  final _deltaController = StreamController<Map<int, String>>.broadcast();
  bool _listening = false;

  Stream<Map<int, String>> get deltas => _deltaController.stream;

  void _ensureListening() {
    if (_listening) return;
    _listening = true;
    final accumulated = <int, String>{};
    _process.stdout.transform(utf8.decoder).transform(const LineSplitter()).listen((line) {
      if (line.trim().isEmpty) return;
      final msg = jsonDecode(line) as Map<String, dynamic>;
      final id = msg['id'] as int?;
      if (msg['type'] == 'delta' && id != null) {
        accumulated[id] = (accumulated[id] ?? '') + (msg['text'] as String);
        _deltaController.add({id: accumulated[id]!});
        return;
      }
      final completer = id != null ? _pending.remove(id) : null;
      completer?.complete(msg);
    });
  }

  Future<Map<String, dynamic>> _request(Map<String, dynamic> body) {
    _ensureListening();
    final id = _nextId++;
    _activeId = id;
    final completer = Completer<Map<String, dynamic>>();
    _pending[id] = completer;
    _process.stdin.writeln(jsonEncode({...body, 'id': id}));
    return completer.future;
  }

  int? _activeId;
  int? get activeId => _activeId;

  Stream<String> partials() => deltas.map((m) => m[activeId]).where((t) => t != null).cast<String>();

  Future<JarvisReply> sendMessage(String text, {Map<String, dynamic>? attachment}) async {
    final body = <String, dynamic>{'type': 'message', 'text': text};
    if (attachment != null) body['attachment'] = attachment;
    final resp = await _request(body);
    if (resp['type'] == 'error') throw StateError(resp['message'] as String);
    return JarvisReply.fromJson(resp);
  }

  Future<JarvisReply> confirm(String yesOrNo) => sendMessage(yesOrNo);
  Future<void> clearMemory() async {
    await _request({'type': 'clear_memory'});
  }
  Future<List<String>> listTools() async {
    final resp = await _request({'type': 'tools'});
    return (resp['tools'] as List).cast<String>();
  }
  Future<void> dispose() async {
    _process.kill();
    await _process.exitCode;
  }
}
