import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:flutter_tts/flutter_tts.dart';
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
  final FlutterTts _tts = FlutterTts();
  StreamSubscription<String>? _partialSub;
  Timer? _visualTimer;
  Timer? _voiceRestartTimer;
  bool _busy = false;
  bool _voiceReady = false;
  bool _voiceListening = false;
  bool _voicePaused = false;
  bool _voiceInitStarted = false;
  String _status = 'Инициализация…';
  String _streamText = '';
  JarvisVisualState _visualState = JarvisVisualState.idle;
  bool get _android => Platform.isAndroid;

  @override
  void initState() {
    super.initState();
    if (_android) {
      _status = 'Настройте AI-провайдера';
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _initVoice();
      });
    } else {
      _connectDesktop();
    }
  }

  Future<void> _initVoice() async {
    if (_voiceInitStarted || !mounted || !_android) return;
    _voiceInitStarted = true;
    try {
      final available = await _speech.initialize(
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
        setState(() => _status = 'Микрофон/распознавание речи недоступно');
        return;
      }
      _voiceReady = true;
      setState(() => _status = 'JARVIS ждёт: скажите «Джарвис»');
      await _startVoiceListening();
    } catch (e) {
      if (mounted) setState(() => _status = 'Ошибка голоса: $e');
    }
  }

  void _scheduleVoiceRestart([Duration delay = const Duration(milliseconds: 500)]) {
    if (!_android || !_voiceReady || _voicePaused || _busy || !mounted) return;
    _voiceRestartTimer?.cancel();
    _voiceRestartTimer = Timer(delay, _startVoiceListening);
  }

  Future<void> _startVoiceListening() async {
    if (!_android || !_voiceReady || _voicePaused || _voiceListening || _busy || !mounted) return;
    try {
      _voiceListening = true;
      await _speech.listen(
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
    final wake = lower.contains('джарвис') || lower.contains('jarvis') || lower.contains('джарвисе');
    if (!wake) return;
    _voicePaused = true;
    _voiceRestartTimer?.cancel();
    try { await _speech.stop(); } catch (_) {}
    _voiceListening = false;
    var command = phrase
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
      await _tts.setLanguage('ru-RU');
      await _tts.setSpeechRate(0.48);
      await _tts.setVolume(1.0);
      await _tts.setPitch(1.0);
      _setVisual(JarvisVisualState.speaking);
      await _tts.stop();
      await _tts.speak(text.trim());
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
      _voicePaused = false;
      _scheduleVoiceRestart();
    } catch (e) {
      if (mounted) setState(() => _status = 'Ошибка AI: $e');
      _setVisual(JarvisVisualState.error);
    }
  }

  Future<void> _finishConnect() async {
    final tools = await _jarvis!.listTools();
    if (!mounted) return;
    setState(() => _status = _android ? 'JARVIS готов · скажите «Джарвис»' : 'JARVIS подключён · инструментов: ${tools.length}');
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
    try { await _speech.stop(); } catch (_) {}
    _voiceListening = false;
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
              decoration: const InputDecoration(labelText: 'API key', hintText: 'можно вставить только сам ключ или Bearer ...')),
            const SizedBox(height: 12),
            const Text('Android работает самостоятельно. Голос: «Джарвис» + команда. Ответ озвучивается.', style: TextStyle(fontSize: 12)),
          ]),
        ),
        actions: [
          TextButton(onPressed: () { Navigator.pop(ctx); _voicePaused = false; _scheduleVoiceRestart(); }, child: const Text('Отмена')),
          FilledButton(onPressed: () { Navigator.pop(ctx); _connectAndroid(); }, child: const Text('Сохранить и подключить')),
        ],
      ),
    );
  }

  Future<void> _send(String text, {bool fromVoice = false}) async {
    text = text.trim();
    if (text.isEmpty || _jarvis == null || _busy) return;
    if (_android && !fromVoice) {
      _voicePaused = true;
      try { await _speech.stop(); } catch (_) {}
      _voiceListening = false;
    }
    _input.clear();
    setState(() { _messages.add(_Msg(text, isUser: true)); _busy = true; _streamText = ''; _visualState = JarvisVisualState.listening; });
    await Future<void>.delayed(const Duration(milliseconds: 180));
    if (!mounted) return;
    setState(() => _visualState = JarvisVisualState.thinking);
    try {
      final reply = await _jarvis!.sendMessage(text);
      if (mounted) {
        setState(() {
          _messages.add(_Msg(reply.text, isUser: false));
          _visualState = JarvisVisualState.speaking;
        });
      }
      if (_android) await _speak(reply.text);
      _returnToIdle(const Duration(milliseconds: 1800));
    } catch (e) {
      if (mounted) {
        setState(() => _messages.add(_Msg('Ошибка: $e', isUser: false)));
        _setVisual(JarvisVisualState.error);
      }
      if (_android) await _speak('Произошла ошибка');
    } finally {
      if (mounted) setState(() { _busy = false; _streamText = ''; });
      if (_visualState == JarvisVisualState.thinking) _returnToIdle();
      if (_android && !fromVoice) {
        _voicePaused = false;
        _scheduleVoiceRestart(const Duration(milliseconds: 700));
      }
    }
  }

  Future<void> _clearMemory() async {
    try {
      await _jarvis?.clearMemory();
      if (mounted) {
        setState(() => _messages.add(_Msg('История диалога очищена.', isUser: false)));
        _setVisual(JarvisVisualState.confirmation);
        _returnToIdle();
      }
    } catch (e) {
      if (mounted) {
        setState(() => _messages.add(_Msg('Ошибка: $e', isUser: false)));
        _setVisual(JarvisVisualState.error);
      }
    }
  }

  @override
  void dispose() {
    _visualTimer?.cancel();
    _voiceRestartTimer?.cancel();
    _partialSub?.cancel();
    _speech.cancel();
    _tts.stop();
    _jarvis?.dispose();
    _input.dispose(); _endpoint.dispose(); _apiKey.dispose(); _model.dispose(); _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('JARVIS'), actions: [
      if (_android) IconButton(onPressed: _settings, tooltip: 'Настройки AI', icon: const Icon(Icons.settings)),
      if (_android) IconButton(onPressed: () {
        _voicePaused = !_voicePaused;
        if (_voicePaused) { _speech.stop(); _voiceListening = false; }
        else { _scheduleVoiceRestart(); }
        if (mounted) setState(() => _status = _voicePaused ? 'Голос выключен' : 'JARVIS ждёт: скажите «Джарвис»');
      }, tooltip: 'Голос', icon: Icon(_voicePaused ? Icons.mic_off : Icons.mic)),
    ]),
    body: Column(children: [
      const SizedBox(height: 8),
      SizedBox(width: 270, height: 270, child: JarvisReactor(color: kCyan, state: _visualState)),
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
