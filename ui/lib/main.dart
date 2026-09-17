import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';

import 'jarvis_client.dart';
import 'jarvis_reactor.dart';
import 'native_voice.dart';

const kCyan = Color(0xFF37D5EE);
const kBg = Color(0xFF05080F);
const kPanel = Color(0xFF0D1622);

void main() {
  FlutterError.onError = (details) {
    FlutterError.dumpErrorToConsole(details);
  };
  runZonedGuarded(() => runApp(const JarvisApp()), (error, stack) {
    debugPrint('JARVIS uncaught error: $error\n$stack');
  });
}

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
  const _Msg(this.text, this.isUser);
  final String text;
  final bool isUser;
}

class JarvisHomePage extends StatefulWidget {
  const JarvisHomePage({super.key});
  @override
  State<JarvisHomePage> createState() => _JarvisHomePageState();
}

class _JarvisHomePageState extends State<JarvisHomePage> {
  final _input = TextEditingController();
  final _endpoint = TextEditingController();
  final _apiKey = TextEditingController();
  final _model = TextEditingController();
  final _scroll = ScrollController();
  final _messages = <_Msg>[];
  final _voice = NativeVoice();
  final _tts = FlutterTts();

  JarvisIpc? _client;
  StreamSubscription<NativeVoiceEvent>? _voiceSub;
  Timer? _voiceRestart;

  bool _android = false;
  bool _voiceEnabled = false;
  bool _waitingForCommand = false;
  bool _busy = false;
  bool _settingsOpen = false;
  String _status = 'JARVIS запускается…';
  String _stream = '';
  JarvisVisualState _visual = JarvisVisualState.idle;

  @override
  void initState() {
    super.initState();
    _android = Platform.isAndroid;
    _voiceSub = _voice.events.listen(_onVoiceEvent, onError: (Object e) {
      if (mounted) setState(() => _status = 'Ошибка голосового слоя: $e');
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_android) {
        _startNativeVoice();
      } else {
        _connectDesktop();
      }
    });
  }

  Future<void> _startNativeVoice() async {
    try {
      final available = await _voice.isAvailable();
      if (!available) {
        if (mounted) setState(() => _status = 'Android не предоставил службу распознавания речи');
        return;
      }
      _voiceEnabled = true;
      if (mounted) setState(() => _status = 'Голос включён. Ожидаю «Джарвис»');
      await _voice.start();
    } catch (e) {
      if (mounted) setState(() => _status = 'Голос недоступен: $e');
    }
  }

  void _onVoiceEvent(NativeVoiceEvent event) {
    if (!mounted) return;
    if (event.type == 'permission') {
      if (event.value == 'granted') {
        setState(() => _status = 'Микрофон разрешён. Ожидаю «Джарвис»');
        _voice.start();
      } else {
        setState(() => _status = 'Нужен доступ к микрофону');
      }
      return;
    }
    if (event.type == 'partial') {
      return;
    }
    if (event.type == 'error') {
      _scheduleVoiceRestart();
      return;
    }
    if (event.type != 'result') return;

    final phrase = event.value.trim();
    if (phrase.isEmpty) {
      _scheduleVoiceRestart();
      return;
    }

    final lower = phrase.toLowerCase();
    final wake = lower.contains('джарвис') || lower.contains('jarvis');
    if (!_waitingForCommand && !wake) {
      _scheduleVoiceRestart();
      return;
    }

    final command = phrase
        .replaceFirst(RegExp(r'\bджарвис(?:е)?\b', caseSensitive: false), '')
        .replaceFirst(RegExp(r'\bjarvis\b', caseSensitive: false), '')
        .trim();

    if (wake && command.isEmpty) {
      _waitingForCommand = true;
      _setVisual(JarvisVisualState.listening);
      _speak('Слушаю');
      _scheduleVoiceRestart(const Duration(milliseconds: 700));
      return;
    }

    _waitingForCommand = false;
    if (mounted) setState(() => _status = 'Команда: $command');
    _send(command, fromVoice: true).whenComplete(() => _scheduleVoiceRestart());
  }

  void _scheduleVoiceRestart([Duration delay = const Duration(milliseconds: 700)]) {
    if (!_android || !_voiceEnabled || _settingsOpen || _busy || !mounted) return;
    _voiceRestart?.cancel();
    _voiceRestart = Timer(delay, () {
      if (mounted && !_settingsOpen && !_busy) _voice.start();
    });
  }

  Future<void> _speak(String text) async {
    try {
      await _tts.setLanguage('ru-RU');
      await _tts.setSpeechRate(0.48);
      await _tts.stop();
      _setVisual(JarvisVisualState.speaking);
      await _tts.speak(text);
    } catch (e) {
      debugPrint('TTS error: $e');
    }
  }

  void _setVisual(JarvisVisualState state) {
    if (mounted) setState(() => _visual = state);
  }

  Future<void> _connectDesktop() async {
    try {
      final dir = File(Platform.resolvedExecutable).parent.path;
      final exe = '$dir${Platform.pathSeparator}jarvis.exe';
      _client = await (File(exe).existsSync()
          ? JarvisIpc.spawn(exe)
          : JarvisIpc.spawn('python', ['-m', 'agent', '--ipc']));
      if (mounted) setState(() => _status = 'JARVIS подключён');
    } catch (e) {
      if (mounted) setState(() => _status = 'Desktop-агент не запущен: $e');
      _setVisual(JarvisVisualState.error);
    }
  }

  Future<void> _connectAndroid() async {
    final endpoint = _endpoint.text.trim();
    if (endpoint.isEmpty) {
      setState(() => _status = 'Укажите endpoint AI');
      return;
    }
    _setVisual(JarvisVisualState.thinking);
    setState(() => _status = 'Подключение к AI…');
    try {
      final old = _client;
      _client = null;
      await old?.dispose();
      _client = await JarvisIpc.connectAi(endpoint, apiKey: _apiKey.text.trim(), model: _model.text.trim());
      setState(() => _status = 'AI подключён · ожидаю «Джарвис»');
      _setVisual(JarvisVisualState.confirmation);
    } catch (e) {
      setState(() => _status = 'Ошибка подключения: $e');
      _setVisual(JarvisVisualState.error);
    }
  }

  Future<void> _settings() async {
    _settingsOpen = true;
    _voiceRestart?.cancel();
    await _voice.stop();
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('AI-провайдер'),
        content: SingleChildScrollView(
          child: Column(children: [
            TextField(controller: _endpoint, keyboardType: TextInputType.url, decoration: const InputDecoration(labelText: 'OpenAI-compatible endpoint')),
            TextField(controller: _model, decoration: const InputDecoration(labelText: 'Модель')),
            TextField(controller: _apiKey, obscureText: true, decoration: const InputDecoration(labelText: 'API key')),
          ]),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Отмена')),
          FilledButton(onPressed: () { Navigator.pop(ctx); _connectAndroid(); }, child: const Text('Подключить')),
        ],
      ),
    );
    _settingsOpen = false;
    _scheduleVoiceRestart(const Duration(milliseconds: 400));
  }

  Future<void> _send(String text, {bool fromVoice = false}) async {
    final clean = text.trim();
    if (clean.isEmpty || _busy) return;
    final client = _client;
    if (client == null) {
      final message = 'Сначала подключите AI в настройках';
      setState(() => _status = message);
      if (fromVoice) await _speak(message);
      return;
    }

    setState(() {
      _busy = true;
      _stream = '';
      _messages.add(_Msg(clean, true));
      _visual = JarvisVisualState.thinking;
    });
    try {
      final reply = await client.sendMessage(clean);
      if (!mounted) return;
      setState(() {
        _messages.add(_Msg(reply.text, false));
        _status = 'Готов';
        _visual = JarvisVisualState.confirmation;
      });
      if (fromVoice) await _speak(reply.text);
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scroll.hasClients) _scroll.animateTo(_scroll.position.maxScrollExtent, duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
      });
    } catch (e) {
      if (!mounted) return;
      final message = 'Ошибка AI: $e';
      setState(() { _messages.add(_Msg(message, false)); _status = message; _visual = JarvisVisualState.error; });
      if (fromVoice) await _speak(message);
    } finally {
      if (mounted) {
        setState(() => _busy = false);
        _scheduleVoiceRestart();
      }
    }
  }

  @override
  void dispose() {
    _voiceRestart?.cancel();
    _voiceSub?.cancel();
    _voice.stop();
    _client?.dispose();
    _input.dispose();
    _endpoint.dispose();
    _apiKey.dispose();
    _model.dispose();
    _scroll.dispose();
    _tts.stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('JARVIS'),
        actions: [
          if (_android) IconButton(onPressed: _settings, icon: const Icon(Icons.settings)),
          if (_android) IconButton(onPressed: () async { if (_voiceEnabled) { await _voice.stop(); setState(() => _voiceEnabled = false); } else { setState(() => _voiceEnabled = true); await _voice.start(); } }, icon: Icon(_voiceEnabled ? Icons.mic : Icons.mic_off)),
        ],
      ),
      body: Column(children: [
        Expanded(child: Center(child: SizedBox(width: 360, height: 360, child: JarvisReactor(state: _visual)))),
        Padding(padding: const EdgeInsets.symmetric(horizontal: 16), child: Text(_status, textAlign: TextAlign.center)),
        if (_messages.isNotEmpty) SizedBox(height: 150, child: ListView.builder(controller: _scroll, itemCount: _messages.length, itemBuilder: (_, i) { final m = _messages[i]; return Padding(padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4), child: Align(alignment: m.isUser ? Alignment.centerRight : Alignment.centerLeft, child: DecoratedBox(decoration: BoxDecoration(color: kPanel, borderRadius: BorderRadius.circular(12)), child: Padding(padding: const EdgeInsets.all(10), child: Text(m.text))))); })),
        SafeArea(child: Padding(padding: const EdgeInsets.all(10), child: Row(children: [Expanded(child: TextField(controller: _input, onSubmitted: _send, decoration: const InputDecoration(hintText: 'Команда…'))), IconButton(onPressed: () { final t = _input.text; _input.clear(); _send(t); }, icon: const Icon(Icons.send))]))),
      ]),
    );
  }
}
