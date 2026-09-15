import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
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
  final stt.SpeechToText _speech = stt.SpeechToText();
  StreamSubscription<String>? _partialSub;
  Timer? _visualTimer;
  bool _busy = false;
  bool _speechReady = false;
  bool _listening = false;
  String _status = 'Инициализация…';
  String _streamText = '';
  JarvisVisualState _visualState = JarvisVisualState.idle;
  bool get _android => Platform.isAndroid;

  @override
  void initState() {
    super.initState();
    if (_android) {
      _status = 'Настройте OpenRouter';
      _initSpeech();
    } else {
      _connectDesktop();
    }
  }

  Future<void> _initSpeech() async {
    try {
      final available = await _speech.initialize(
        onStatus: (status) {
          if (!mounted) return;
          final active = status == 'listening';
          setState(() => _listening = active);
          if (!active && !_busy && _jarvis != null) _returnToIdle();
        },
        onError: (error) {
          if (!mounted) return;
          setState(() => _status = 'Голос: ${error.errorMsg}');
          _setVisual(JarvisVisualState.error);
        },
      );
      if (!mounted) return;
      setState(() {
        _speechReady = available;
        if (!available && _jarvis != null) _status = 'AI подключён · голос недоступен на устройстве';
      });
    } catch (e) {
      if (mounted) setState(() => _status = 'Голос недоступен: $e');
    }
  }

  Future<void> _toggleListening() async {
    if (!_android || _busy || _jarvis == null) return;
    if (!_speechReady) {
      await _initSpeech();
      if (!_speechReady) return;
    }
    if (_listening) {
      await _speech.stop();
      if (mounted) setState(() => _listening = false);
      _returnToIdle();
      return;
    }
    _setVisual(JarvisVisualState.listening);
    if (mounted) setState(() => _status = 'Слушаю…');
    await _speech.listen(
      localeId: 'ru_RU',
      listenMode: stt.ListenMode.confirmation,
      partialResults: true,
      onResult: (result) {
        if (!mounted) return;
        final text = result.recognizedWords.trim();
        if (text.isNotEmpty) _input.text = text;
        if (result.finalResult && text.isNotEmpty) {
          _speech.stop();
          _listening = false;
          _send(text);
        }
      },
    );
  }

  void _setVisual(JarvisVisualState state) {
    _visualTimer?.cancel();
    if (mounted) setState(() => _visualState = state);
  }

  void _returnToIdle([Duration delay = const Duration(milliseconds: 900)]) {
    _visualTimer?.cancel();
    _visualTimer = Timer(delay, () {
      if (mounted && !_busy && !_listening) setState(() => _visualState = JarvisVisualState.idle);
    });
  }

  Future<void> _connectDesktop() async {
    try {
      final dir = File(Platform.resolvedExecutable).parent.path;
      final exe = '$dir${Platform.pathSeparator}jarvis.exe';
      _jarvis = await (File(exe).existsSync() ? JarvisIpc.spawn(exe) : JarvisIpc.spawn('python', ['-m', 'agent', '--ipc']));
      await _finishConnect();
    } catch (e) {
      if (mounted) { setState(() => _status = 'Агент не запущен: $e'); _setVisual(JarvisVisualState.error); }
    }
  }

  Future<void> _connectAndroid() async {
    final endpoint = _endpoint.text.trim();
    final model = _model.text.trim();
    final key = _apiKey.text.trim();
    if (endpoint.isEmpty) { if (mounted) setState(() => _status = 'Укажите endpoint AI'); _setVisual(JarvisVisualState.error); return; }
    if (key.isEmpty) { if (mounted) setState(() => _status = 'Укажите API key OpenRouter'); _setVisual(JarvisVisualState.error); return; }
    setState(() => _status = 'Подключение к OpenRouter…');
    _setVisual(JarvisVisualState.thinking);
    try {
      await _jarvis?.dispose();
      _jarvis = await JarvisIpc.connectAi(endpoint, apiKey: key, model: model);
      await _finishConnect();
    } catch (e) { if (mounted) setState(() => _status = 'Ошибка AI: $e'); _setVisual(JarvisVisualState.error); }
  }

  Future<void> _finishConnect() async {
    final tools = await _jarvis!.listTools();
    if (!mounted) return;
    setState(() => _status = _android ? 'OpenRouter подключён · JARVIS готов' : 'JARVIS подключён · инструментов: ${tools.length}');
    _setVisual(JarvisVisualState.confirmation);
    _returnToIdle(const Duration(milliseconds: 1100));
    _partialSub?.cancel();
    _partialSub = _jarvis!.partials().listen((text) {
      if (mounted) setState(() { _streamText = text; if (text.isNotEmpty) _visualState = JarvisVisualState.speaking; });
    });
  }

  Future<void> _settings() async {
    if (!_android) return;
    if (_endpoint.text.isEmpty) _endpoint.text = 'https://openrouter.ai/api/v1';
    if (_model.text.isEmpty) _model.text = 'openrouter/free';
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('OpenRouter — AI-провайдер'),
        content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: _endpoint, keyboardType: TextInputType.url, decoration: const InputDecoration(labelText: 'Endpoint', hintText: 'https://openrouter.ai/api/v1')),
          TextField(controller: _model, decoration: const InputDecoration(labelText: 'Модель', hintText: 'openrouter/free')),
          TextField(controller: _apiKey, obscureText: true, decoration: const InputDecoration(labelText: 'API key', hintText: 'sk-or-v1-...')),
          const SizedBox(height: 12),
          const Text('API key обязателен. Можно вставить как sk-or-v1-... или вместе с Bearer — JARVIS сам уберёт Bearer.', style: TextStyle(fontSize: 12)),
        ])),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Отмена')),
          FilledButton(onPressed: () { Navigator.pop(ctx); _connectAndroid(); }, child: const Text('Подключить')),
        ],
      ),
    );
  }

  Future<void> _send(String text) async {
    text = text.trim();
    if (text.isEmpty || _jarvis == null || _busy) return;
    _input.clear();
    setState(() { _messages.add(_Msg(text, isUser: true)); _busy = true; _streamText = ''; _visualState = JarvisVisualState.listening; });
    await Future<void>.delayed(const Duration(milliseconds: 180));
    if (!mounted) return;
    setState(() => _visualState = JarvisVisualState.thinking);
    try {
      final reply = await _jarvis!.sendMessage(text);
      if (mounted) setState(() { _messages.add(_Msg(reply.text, isUser: false)); _visualState = JarvisVisualState.speaking; });
      _returnToIdle(const Duration(milliseconds: 1800));
    } catch (e) {
      if (mounted) { setState(() => _messages.add(_Msg('Ошибка: $e', isUser: false))); _setVisual(JarvisVisualState.error); }
    } finally {
      if (mounted) setState(() { _busy = false; _streamText = ''; });
      if (_visualState == JarvisVisualState.thinking) _returnToIdle();
    }
  }

  Future<void> _clearMemory() async {
    try {
      await _jarvis?.clearMemory();
      if (mounted) { setState(() => _messages.add(_Msg('История диалога очищена.', isUser: false))); _setVisual(JarvisVisualState.confirmation); _returnToIdle(); }
    } catch (e) {
      if (mounted) { setState(() => _messages.add(_Msg('Ошибка: $e', isUser: false))); _setVisual(JarvisVisualState.error); }
    }
  }

  @override
  void dispose() {
    _visualTimer?.cancel(); _partialSub?.cancel(); _speech.stop(); _jarvis?.dispose();
    _input.dispose(); _endpoint.dispose(); _apiKey.dispose(); _model.dispose(); _scroll.dispose(); super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('JARVIS'), actions: [if (_android) IconButton(onPressed: _settings, tooltip: 'Настройки AI', icon: const Icon(Icons.settings))]),
    body: Column(children: [
      const SizedBox(height: 8),
      SizedBox(width: 270, height: 270, child: JarvisReactor(color: kCyan, state: _visualState)),
      Padding(padding: const EdgeInsets.symmetric(horizontal: 16), child: Text(_status, style: const TextStyle(color: kCyan, fontSize: 12), textAlign: TextAlign.center)),
      Expanded(child: ListView.builder(controller: _scroll, padding: const EdgeInsets.all(16), itemCount: _messages.length, itemBuilder: (_, i) {
        final m = _messages[i];
        return Align(alignment: m.isUser ? Alignment.centerRight : Alignment.centerLeft, child: Container(margin: const EdgeInsets.symmetric(vertical: 4), padding: const EdgeInsets.all(12), constraints: const BoxConstraints(maxWidth: 560), decoration: BoxDecoration(color: m.isUser ? kCyan.withValues(alpha: .15) : kPanel, borderRadius: BorderRadius.circular(12)), child: SelectableText(m.text)));
      })),
      if (_busy && _streamText.isNotEmpty) Padding(padding: const EdgeInsets.all(8), child: Text('$_streamText▌')),
      if (_android && _jarvis == null) Padding(padding: const EdgeInsets.symmetric(horizontal: 16), child: FilledButton.icon(onPressed: _settings, icon: const Icon(Icons.settings), label: const Text('Настроить OpenRouter'))),
      Padding(padding: const EdgeInsets.fromLTRB(12, 4, 12, 12), child: Row(children: [
        if (_android) IconButton(onPressed: _busy || _jarvis == null ? null : _toggleListening, tooltip: _listening ? 'Остановить прослушивание' : 'Голосовой ввод', icon: Icon(_listening ? Icons.mic : Icons.mic_none, color: _listening ? kCyan : null)),
        Expanded(child: TextField(controller: _input, onSubmitted: _send, decoration: const InputDecoration(hintText: 'Сообщение…', filled: true, fillColor: kPanel))),
        IconButton(onPressed: _busy || _jarvis == null ? null : () => _send(_input.text), icon: const Icon(Icons.send, color: kCyan)),
        IconButton(onPressed: _busy || _jarvis == null ? null : _clearMemory, icon: const Icon(Icons.delete_outline)),
      ])),
    ]),
  );
}
