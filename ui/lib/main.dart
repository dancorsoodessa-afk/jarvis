import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
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
        title: 'JARVIS',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          brightness: Brightness.dark,
          scaffoldBackgroundColor: kBg,
          colorScheme: ColorScheme.fromSeed(seedColor: kCyan, brightness: Brightness.dark),
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
  final _endpoint = TextEditingController();
  final _apiKey = TextEditingController();
  final _model = TextEditingController();
  final _scroll = ScrollController();
  final _messages = <_Msg>[];
  stt.SpeechToText? _speech;
  FlutterTts? _tts;
  StreamSubscription<String>? _partialSub;
  Timer? _visualTimer;
  Timer? _voiceRestartTimer;
  bool _busy = false;
  bool _voiceReady = false;
  bool _voiceListening = false;
  bool _voicePaused = true;
  bool _voiceInitStarted = false;
  String _status = 'JARVIS запускается…';
  String _streamText = '';
  JarvisVisualState _visualState = JarvisVisualState.idle;
  bool get _android => Platform.isAndroid;

  @override
  void initState() {
    super.initState();
    if (_android) {
      _status = 'JARVIS готов. Нажмите микрофон для голоса.';
    } else {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _connectDesktop();
      });
    }
  }

  Future<void> _initVoice() async {
    if (_voiceInitStarted || !mounted || !_android) return;
    _voiceInitStarted = true;
    try {
      final speech = stt.SpeechToText();
      _speech = speech;
      final available = await speech.initialize(
        onStatus: (status) {
          if (!_android || _voicePaused) return;
          if (status == 'done' || status == 'notListening') {
            _voiceListening = false;
            _scheduleVoiceRestart();
          }
        },
        onError: (_) {
          _voiceListening = false;
          _scheduleVoiceRestart(const Duration(milliseconds: 1200));
        },
      );
      if (!mounted) return;
      if (!available) {
        setState(() => _status = 'Распознавание речи недоступно');
        return;
      }
      _voiceReady = true;
      _voicePaused = false;
      setState(() => _status = 'Голос включён. Скажите «Джарвис».');
      await _startVoiceListening();
    } catch (e) {
      if (mounted) setState(() => _status = 'Голос недоступен: $e');
    }
  }

  void _scheduleVoiceRestart([Duration delay = const Duration(milliseconds: 500)]) {
    if (!_android || !_voiceReady || _voicePaused || _busy || !mounted) return;
    _voiceRestartTimer?.cancel();
    _voiceRestartTimer = Timer(delay, _startVoiceListening);
  }

  Future<void> _startVoiceListening() async {
    final speech = _speech;
    if (!_android || speech == null || !_voiceReady || _voicePaused || _voiceListening || _busy || !mounted) return;
    try {
      _voiceListening = true;
      await speech.listen(
        onResult: _onVoiceResult,
        listenFor: const Duration(seconds: 20),
        pauseFor: const Duration(seconds: 3),
        partialResults: true,
        listenMode: stt.ListenMode.confirmation,
      );
    } catch (_) {
      _voiceListening = false;
      _scheduleVoiceRestart(const Duration(seconds: 1));
    }
  }

  Future<void> _onVoiceResult(SpeechRecognitionResult result) async {
    if (!result.finalResult) return;
    final phrase = result.recognizedWords.trim();
    if (phrase.isEmpty || !_android || _voicePaused || _busy) return;
    final lower = phrase.toLowerCase();
    final wake = lower.contains('джарвис') || lower.contains('jarvis');
    if (!wake) return;
    _voicePaused = true;
    _voiceRestartTimer?.cancel();
    try { await _speech?.stop(); } catch (_) {}
    _voiceListening = false;
    final command = phrase
        .replaceFirst(RegExp(r'джарвис(?:е)?', caseSensitive: false), '')
        .replaceFirst(RegExp(r'jarvis', caseSensitive: false), '')
        .trim();
    if (command.isEmpty) {
      _setVisual(JarvisVisualState.listening);
      await _speak('Слушаю');
      _voicePaused = false;
      _scheduleVoiceRestart();
      return;
    }
    if (mounted) setState(() => _status = 'Команда: $command');
    await _send(command, fromVoice: true);
    _voicePaused = false;
    _scheduleVoiceRestart(const Duration(milliseconds: 700));
  }

  Future<void> _speak(String text) async {
    if (!_android || text.trim().isEmpty || !mounted) return;
    try {
      final tts = _tts ??= FlutterTts();
      await tts.setLanguage('ru-RU');
      await tts.setSpeechRate(0.48);
      await tts.setVolume(1.0);
      await tts.setPitch(1.0);
      _setVisual(JarvisVisualState.speaking);
      await tts.stop();
      await tts.speak(text.trim());
    } catch (_) {}
  }

  void _setVisual(JarvisVisualState state) {
    _visualTimer?.cancel();
    if (mounted) setState(() => _visualState = state);
  }

  void _returnToIdle([Duration delay = const Duration(milliseconds: 900)]) {
    _visualTimer?.cancel();
    _visualTimer = Timer(delay, () {
      if (mounted && !_busy) setState(() => _visualState = JarvisVisualState.idle);
    });
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
      if (mounted) {
        setState(() => _status = 'Агент не запущен: $e');
        _setVisual(JarvisVisualState.error);
      }
    }
  }

  Future<void> _connectAndroid() async {
    final endpoint = _endpoint.text.trim();
    final model = _model.text.trim();
    if (endpoint.isEmpty) {
      if (mounted) setState(() => _status = 'Укажите endpoint AI');
      _setVisual(JarvisVisualState.error);
      return;
    }
    setState(() => _status = model.isEmpty ? 'Поиск модели и подключение…' : 'Подключение к AI…');
    _setVisual(JarvisVisualState.thinking);
    try {
      await _partialSub?.cancel();
      _partialSub = null;
      final old = _jarvis;
      _jarvis = null;
      await old?.dispose();
      _jarvis = await JarvisIpc.connectAi(endpoint, apiKey: _apiKey.text.trim(), model: model);
      await _finishConnect();
      if (_voiceReady) {
        _voicePaused = false;
        _scheduleVoiceRestart();
      }
    } catch (e) {
      if (mounted) setState(() => _status = 'Ошибка AI: $e');
      _setVisual(JarvisVisualState.error);
    }
  }

  Future<void> _finishConnect() async {
    final tools = await _jarvis!.listTools();
    if (!mounted) return;
    setState(() => _status = _android ? 'JARVIS подключён · скажите «Джарвис»' : 'JARVIS подключён · инструментов: ${tools.length}');
    _setVisual(JarvisVisualState.confirmation);
    _returnToIdle(const Duration(milliseconds: 1100));
    await _partialSub?.cancel();
    _partialSub = _jarvis!.partials().listen((text) {
      if (mounted) {
        setState(() {
          _streamText = text;
          if (text.isNotEmpty) _visualState = JarvisVisualState.speaking;
        });
      }
    });
  }

  Future<void> _settings() async {
    if (!_android) return;
    _voicePaused = true;
    try { await _speech?.stop(); } catch (_) {}
    _voiceListening = false;
    _endpoint.text = _endpoint.text.isEmpty ? const String.fromEnvironment('JARVIS_API_URL', defaultValue: '') : _endpoint.text;
    _model.text = _model.text.isEmpty ? const String.fromEnvironment('JARVIS_MODEL', defaultValue: '') : _model.text;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('AI-провайдер'),
        content: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(controller: _endpoint, keyboardType: TextInputType.url, decoration: const InputDecoration(labelText: 'OpenAI-compatible endpoint', hintText: 'https://example.com/v1')),
            TextField(controller: _model, decoration: const InputDecoration(labelText: 'Модель', hintText: 'необязательно — модель будет найдена автоматически')),
            TextField(controller: _apiKey, obscureText: true, decoration: const InputDecoration(labelText: 'API key')),
            const SizedBox(height: 12),
            const Text('Голос запускается только после нажатия микрофона. Команда активации: «Джарвис».', style: TextStyle(fontSize: 12)),
          ]),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Отмена')),
          FilledButton(onPressed: () { Navigator.pop(ctx); _connectAndroid(); }, child: const Text('Подключить')),
        ],
      ),
    );
    if (mounted && !_voiceInitStarted) _status = 'JARVIS готов. Нажмите микрофон для голоса.';
  }

  Future<void> _toggleVoice() async {
    if (!_android) return;
    if (!_voiceInitStarted) await _initVoice();
    if (!_voiceReady) return;
    _voicePaused = !_voicePaused;
    if (_voicePaused) {
      _voiceRestartTimer?.cancel();
      try { await _speech?.stop(); } catch (_) {}
      _voiceListening = false;
      if (mounted) setState(() => _status = 'Голос выключен');
    } else {
      if (mounted) setState(() => _status = 'Слушаю. Скажите «Джарвис»');
      await _startVoiceListening();
    }
  }

  Future<void> _send(String text, {bool fromVoice = false}) async {
    final clean = text.trim();
    if (clean.isEmpty || _busy) return;
    final client = _jarvis;
    if (client == null) {
      if (mounted) setState(() => _status = 'Сначала подключите AI в настройках');
      if (fromVoice) await _speak('Сначала подключите AI в настройках');
      return;
    }
    setState(() {
      _busy = true;
      _streamText = '';
      _messages.add(_Msg(clean, isUser: true));
      _visualState = JarvisVisualState.thinking;
    });
    _scrollToBottom();
    try {
      final reply = await client.sendMessage(clean);
      if (!mounted) return;
      setState(() {
        _messages.add(_Msg(reply.text, isUser: false));
        _status = reply.needsConfirmation ? 'Требуется подтверждение' : 'Готов';
        _visualState = reply.needsConfirmation ? JarvisVisualState.confirmation : JarvisVisualState.speaking;
      });
      _scrollToBottom();
      if (fromVoice) await _speak(reply.text);
    } catch (e) {
      if (!mounted) return;
      setState(() { _messages.add(_Msg('Ошибка: $e', isUser: false)); _status = 'Ошибка'; _visualState = JarvisVisualState.error; });
      if (fromVoice) await _speak('Произошла ошибка');
    } finally {
      if (mounted) { setState(() => _busy = false); _returnToIdle(); }
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) _scroll.animateTo(_scroll.position.maxScrollExtent, duration: const Duration(milliseconds: 180), curve: Curves.easeOut);
    });
  }

  @override
  void dispose() {
    _voiceRestartTimer?.cancel();
    _visualTimer?.cancel();
    _partialSub?.cancel();
    _speech?.stop();
    _tts?.stop();
    _jarvis?.dispose();
    _input.dispose();
    _endpoint.dispose();
    _apiKey.dispose();
    _model.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('JARVIS'),
        actions: [
          if (_android) IconButton(icon: const Icon(Icons.mic_none), tooltip: 'Голос', onPressed: _toggleVoice),
          if (_android) IconButton(icon: const Icon(Icons.settings), tooltip: 'AI', onPressed: _settings),
        ],
      ),
      body: Column(children: [
        Expanded(child: ListView.builder(controller: _scroll, padding: const EdgeInsets.all(16), itemCount: _messages.length, itemBuilder: (context, i) {
          final m = _messages[i];
          return Align(alignment: m.isUser ? Alignment.centerRight : Alignment.centerLeft, child: Container(
            margin: const EdgeInsets.only(bottom: 10), padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(color: m.isUser ? kPanel : const Color(0xFF111D2B), borderRadius: BorderRadius.circular(14)),
            child: Text(m.text),
          ));
        })),
        if (_streamText.isNotEmpty) Padding(padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6), child: Text(_streamText)),
        Padding(padding: const EdgeInsets.fromLTRB(12, 4, 12, 12), child: Row(children: [
          Expanded(child: TextField(controller: _input, textInputAction: TextInputAction.send, onSubmitted: _send, decoration: const InputDecoration(hintText: 'Команда JARVIS', border: OutlineInputBorder()))),
          const SizedBox(width: 8),
          IconButton.filled(onPressed: _busy ? null : () { final t = _input.text; _input.clear(); _send(t); }, icon: const Icon(Icons.send)),
        ])),
        Padding(padding: const EdgeInsets.only(bottom: 10), child: Text(_status, style: const TextStyle(fontSize: 12))),
      ]),
    );
  }
}
