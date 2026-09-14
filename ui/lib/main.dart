import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'jarvis_client.dart';
import 'jarvis_reactor.dart';

const kCyan = Color(0xFF37D5EE);
const kBg = Color(0xFF05080F);
const kPanel = Color(0xFF0D1622);

void main() => runApp(const JarvisApp());

class JarvisApp extends StatelessWidget {
  const JarvisApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'JARVIS', debugShowCheckedModeBanner: false,
    theme: ThemeData(brightness: Brightness.dark, scaffoldBackgroundColor: kBg,
      colorScheme: ColorScheme.fromSeed(seedColor: kCyan, brightness: Brightness.dark), useMaterial3: true),
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
  final _endpoint = TextEditingController();
  final _apiKey = TextEditingController();
  final _model = TextEditingController();
  final _scroll = ScrollController();
  final _messages = <_Msg>[];
  StreamSubscription<String>? _partialSub;
  bool _busy = false;
  String _status = 'Инициализация…';
  String _streamText = '';
  bool get _android => Platform.isAndroid;

  @override
  void initState() {
    super.initState();
    if (_android) {
      _status = 'Настройте AI-провайдера';
    } else {
      _connectDesktop();
    }
  }

  Future<void> _connectDesktop() async {
    try {
      final dir = File(Platform.resolvedExecutable).parent.path;
      final exe = '$dir${Platform.pathSeparator}jarvis.exe';
      _jarvis = await (File(exe).existsSync()
          ? JarvisIpc.spawn(exe)
          : JarvisIpc.spawn('python', ['-m', 'agent', '--ipc']));
      await _finishConnect();
    } catch (e) {
      if (mounted) setState(() => _status = 'Агент не запущен: $e');
    }
  }

  Future<void> _connectAndroid() async {
    final endpoint = _endpoint.text.trim();
    final model = _model.text.trim();
    if (endpoint.isEmpty) {
      if (mounted) setState(() => _status = 'Укажите endpoint AI');
      return;
    }
    setState(() => _status = model.isEmpty ? 'Поиск модели и подключение…' : 'Подключение к AI…');
    try {
      await _jarvis?.dispose();
      _jarvis = await JarvisIpc.connectAi(endpoint, apiKey: _apiKey.text.trim(), model: model);
      await _finishConnect();
    } catch (e) {
      if (mounted) setState(() => _status = 'Ошибка AI: $e');
    }
  }

  Future<void> _finishConnect() async {
    final tools = await _jarvis!.listTools();
    if (!mounted) return;
    setState(() => _status = _android ? 'JARVIS готов · автономный режим' : 'JARVIS подключён · инструментов: ${tools.length}');
    _partialSub?.cancel();
    _partialSub = _jarvis!.partials().listen((text) {
      if (mounted) setState(() => _streamText = text);
    });
  }

  Future<void> _settings() async {
    if (!_android) return;
    _endpoint.text = _endpoint.text.isEmpty ? const String.fromEnvironment('JARVIS_API_URL', defaultValue: '') : _endpoint.text;
    _model.text = _model.text.isEmpty ? const String.fromEnvironment('JARVIS_MODEL', defaultValue: '') : _model.text;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('AI-провайдер'),
        content: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(controller: _endpoint, keyboardType: TextInputType.url,
              decoration: const InputDecoration(labelText: 'OpenAI-compatible endpoint', hintText: 'https://example.com/v1')),
            TextField(controller: _model, decoration: const InputDecoration(labelText: 'Модель', hintText: 'необязательно — модель будет найдена автоматически')),
            TextField(controller: _apiKey, obscureText: true,
              decoration: const InputDecoration(labelText: 'API key (необязательно)')),
            const SizedBox(height: 12),
            const Text('Android работает самостоятельно и не подключается к JARVIS на ПК. Можно использовать любой OpenAI-compatible AI endpoint.', style: TextStyle(fontSize: 12)),
          ]),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Отмена')),
          FilledButton(onPressed: () { Navigator.pop(ctx); _connectAndroid(); }, child: const Text('Сохранить и подключить')),
        ],
      ),
    );
  }

  Future<void> _send(String text) async {
    text = text.trim();
    if (text.isEmpty || _jarvis == null || _busy) return;
    _input.clear();
    setState(() { _messages.add(_Msg(text, isUser: true)); _busy = true; _streamText = ''; });
    try {
      final reply = await _jarvis!.sendMessage(text);
      if (mounted) setState(() => _messages.add(_Msg(reply.text, isUser: false)));
    } catch (e) {
      if (mounted) setState(() => _messages.add(_Msg('Ошибка: $e', isUser: false)));
    } finally {
      if (mounted) setState(() { _busy = false; _streamText = ''; });
    }
  }

  Future<void> _clearMemory() async {
    try {
      await _jarvis?.clearMemory();
      if (mounted) setState(() => _messages.add(_Msg('История диалога очищена.', isUser: false)));
    } catch (e) {
      if (mounted) setState(() => _messages.add(_Msg('Ошибка: $e', isUser: false)));
    }
  }

  @override
  void dispose() {
    _partialSub?.cancel(); _jarvis?.dispose(); _input.dispose(); _endpoint.dispose(); _apiKey.dispose(); _model.dispose(); _scroll.dispose(); super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('JARVIS'), actions: [if (_android) IconButton(onPressed: _settings, tooltip: 'Настройки AI', icon: const Icon(Icons.settings))]),
    body: Column(children: [
      const SizedBox(height: 8),
      const SizedBox(width: 140, height: 140, child: JarvisReactor(color: kCyan)),
      Padding(padding: const EdgeInsets.symmetric(horizontal: 16), child: Text(_status, style: const TextStyle(color: kCyan, fontSize: 12), textAlign: TextAlign.center)),
      Expanded(child: ListView.builder(controller: _scroll, padding: const EdgeInsets.all(16), itemCount: _messages.length, itemBuilder: (_, i) {
        final m = _messages[i];
        return Align(alignment: m.isUser ? Alignment.centerRight : Alignment.centerLeft, child: Container(
          margin: const EdgeInsets.symmetric(vertical: 4), padding: const EdgeInsets.all(12), constraints: const BoxConstraints(maxWidth: 560),
          decoration: BoxDecoration(color: m.isUser ? kCyan.withValues(alpha: .15) : kPanel, borderRadius: BorderRadius.circular(12)),
          child: SelectableText(m.text),
        ));
      })),
      if (_busy && _streamText.isNotEmpty) Padding(padding: const EdgeInsets.all(8), child: Text('$_streamText▌')),
      if (_android && _jarvis == null) Padding(padding: const EdgeInsets.symmetric(horizontal: 16), child: FilledButton.icon(onPressed: _settings, icon: const Icon(Icons.settings), label: const Text('Настроить AI'))),
      Padding(padding: const EdgeInsets.fromLTRB(12, 4, 12, 12), child: Row(children: [
        Expanded(child: TextField(controller: _input, onSubmitted: _send, decoration: const InputDecoration(hintText: 'Сообщение…', filled: true, fillColor: kPanel))),
        IconButton(onPressed: _busy || _jarvis == null ? null : () => _send(_input.text), icon: const Icon(Icons.send, color: kCyan)),
        IconButton(onPressed: _busy || _jarvis == null ? null : _clearMemory, icon: const Icon(Icons.delete_outline)),
      ])),
    ]),
  );
}
