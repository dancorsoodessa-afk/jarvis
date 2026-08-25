// Flutter-side client for the agent's JSON-lines IPC (agent/ipc.py).
//
// The UI spawns the agent as a child process and never knows which AI
// provider is active — matching docs/ARCHITECTURE.md.
//
// Usage:
//   final jarvis = await JarvisIpc.spawn('jarvis.exe');
//   final reply = await jarvis.sendMessage('привет');
//   print(reply.text);
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

  /// Spawn the agent (exe or `python -m agent`) in IPC mode.
  static Future<JarvisIpc> spawn(String executable,
      [List<String> args = const ['--ipc']]) async {
    final process = await Process.start(executable, args);
    return JarvisIpc._(process);
  }

  final Process _process;
  int _nextId = 0;
  final Map<int, Completer<Map<String, dynamic>>> _pending = {};
  bool _listening = false;

  void _ensureListening() {
    if (_listening) return;
    _listening = true;
    _process.stdout
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .listen((line) {
      if (line.trim().isEmpty) return;
      final msg = jsonDecode(line) as Map<String, dynamic>;
      final id = msg['id'] as int?;
      final completer = id != null ? _pending.remove(id) : null;
      completer?.complete(msg);
      // Messages with id == null (e.g. pushed reminders) can be surfaced
      // through a broadcast stream if the UI needs them.
    });
  }

  Future<Map<String, dynamic>> _request(Map<String, dynamic> body) {
    _ensureListening();
    final id = _nextId++;
    final completer = Completer<Map<String, dynamic>>();
    _pending[id] = completer;
    _process.stdin.writeln(jsonEncode({...body, 'id': id}));
    return completer.future;
  }

  Future<JarvisReply> sendMessage(String text) async {
    final resp = await _request({'type': 'message', 'text': text});
    if (resp['type'] == 'error') {
      throw StateError(resp['message'] as String);
    }
    return JarvisReply.fromJson(resp);
  }

  Future<JarvisReply> confirm(String yesOrNo) => sendMessage(yesOrNo);

  Future<List<String>> listTools() async {
    final resp = await _request({'type': 'tools'});
    return (resp['tools'] as List).cast<String>();
  }

  Future<void> dispose() async {
    _process.kill();
    await _process.exitCode;
  }
}
