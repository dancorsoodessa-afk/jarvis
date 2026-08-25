// Jarvis desktop UI: reactor HUD + chat over JSON-lines IPC.
//
// Layout expected next to the built app:
//   jarvis_ui.exe
//   jarvis.exe            <- built agent (pyinstaller jarvis.spec)
// Fallback: `python -m agent --ipc` if python is on PATH.
//
// Run:  flutter run -d windows   (from this ui/ folder)
import 'dart:io';

import 'package:flutter/material.dart';

import 'jarvis_client.dart';
import 'jarvis_reactor.dart';

void main() => runApp(const JarvisApp());

const kCyan = Color(0xFF37D5EE);
const kBg = Color(0xFF05080F);
const kPanel = Color(0xFF0D1622);

class JarvisApp extends StatelessWidget {
  const JarvisApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'JARVIS',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          brightness: Brightness.dark,
          scaffoldBackgroundColor: kBg,
          colorScheme: ColorScheme.fromSeed(
              seedColor: kCyan, brightness: Brightness.dark, surface: kPanel),
          useMaterial3: true,
        ),
        home: const JarvisHomePage(),
      );
}

class _Msg {
  _Msg(this.text, {required this.isUser});
  final String text;
  final bool isUser;
}

class JarvisHomePage extends StatefulWidget {
  const JarvisHomePage({super.key});

  @override
  State<JarvisHomePage> createState() => _JarvisHomePageState();
}

class _JarvisHomePageState extends State<JarvisHomePage> {
  JarvisIpc? _jarvis;
  final _input = TextEditingController();
  final _scroll = ScrollController();
  final List<_Msg> _messages = [];
  bool _busy = false;
  String _status = 'Подключение к агенту…';

  @override
  void initState() {
    super.initState();
    _connect();
  }

  Future<void> _connect() async {
    final exeDir = File(Platform.resolvedExecutable).parent.path;
    final bundled = '$exeDir${Platform.pathSeparator}jarvis.exe';
    try {
      _jarvis = await (File(bundled).existsSync()
          ? JarvisIpc.spawn(bundled)
          : JarvisIpc.spawn('python', ['-m', 'agent', '--ipc']));
      final tools = await _jarvis!.listTools();
      setState(() => _status = 'Агент готов · инструментов: ${tools.length}');
    } catch (e) {
      setState(() => _status = 'Агент не запущен: $e');
    }
  }

  Future<void> _send(String text) async {
    text = text.trim();
    if (text.isEmpty || _jarvis == null || _busy) return;
    _input.clear();
    setState(() {
      _messages.add(_Msg(text, isUser: true));
      _busy = true;
    });
    try {
      var reply = await _jarvis!.sendMessage(text);
      if (reply.needsConfirmation && mounted) {
        final ok = await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('Подтверждение'),
            content: Text(reply.text),
            actions: [
              TextButton(
                  onPressed: () => Navigator.pop(ctx, false),
                  child: const Text('Отмена')),
              FilledButton(
                  onPressed: () => Navigator.pop(ctx, true),
                  child: const Text('Выполнить')),
            ],
          ),
        );
        reply = await _jarvis!.sendMessage(ok == true ? 'да' : 'нет');
      }
      setState(() => _messages.add(_Msg(reply.text, isUser: false)));
    } catch (e) {
      setState(() => _messages.add(_Msg('Ошибка: $e', isUser: false)));
    } finally {
      setState(() => _busy = false);
      await Future.delayed(const Duration(milliseconds: 50));
      if (_scroll.hasClients) {
        _scroll.jumpTo(_scroll.position.maxScrollExtent);
      }
    }
  }

  @override
  void dispose() {
    _jarvis?.dispose();
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: Column(
          children: [
            const SizedBox(height: 24),
            const SizedBox(
                width: 160, height: 160, child: JarvisReactor(color: kCyan)),
            const SizedBox(height: 8),
            Text(_status,
                style: const TextStyle(color: kCyan, fontSize: 12),
                textAlign: TextAlign.center),
            const SizedBox(height: 8),
            Expanded(
              child: ListView.builder(
                controller: _scroll,
                padding: const EdgeInsets.all(16),
                itemCount: _messages.length,
                itemBuilder: (_, i) => _bubble(_messages[i]),
              ),
            ),
            if (_busy)
              const Padding(
                  padding: EdgeInsets.only(bottom: 4),
                  child: SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: kCyan))),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _input,
                      onSubmitted: _send,
                      decoration: InputDecoration(
                        hintText: 'Сообщение или /команда…',
                        filled: true,
                        fillColor: kPanel,
                        border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                            borderSide: BorderSide.none),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton(
                      onPressed: _busy ? null : () => _send(_input.text),
                      icon: const Icon(Icons.send, color: kCyan)),
                ],
              ),
            ),
          ],
        ),
      );

  Widget _bubble(_Msg m) => Align(
        alignment: m.isUser ? Alignment.centerRight : Alignment.centerLeft,
        child: Container(
          margin: const EdgeInsets.symmetric(vertical: 4),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          constraints: const BoxConstraints(maxWidth: 520),
          decoration: BoxDecoration(
            color: m.isUser ? kCyan.withOpacity(0.15) : kPanel,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
                color: m.isUser ? kCyan.withOpacity(0.4) : Colors.white10),
          ),
          child: SelectableText(m.text),
        ),
      );
}
