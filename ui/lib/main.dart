import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:flutter_tts/flutter_tts.dart';
import 'jarvis_client.dart';
import 'jarvis_reactor.dart';

const kCyan = Color(0xFF37D5EE);
const kBg = Color(0xFF05080F);
const kPanel = Color(0xFF0D1622);
const kFreeModel = 'qwen/qwen3-235b-a22b-2507:free';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runZonedGuarded(() => runApp(const JarvisApp()), (error, stack) {
    debugPrint('JARVIS error: $error');
    debugPrintStack(stackTrace: stack);
  });
}

class JarvisApp extends StatelessWidget {
  const JarvisApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'JARVIS',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(brightness: Brightness.dark, scaffoldBackgroundColor: kBg, colorScheme: ColorScheme.fromSeed(seedColor: kCyan, brightness: Brightness.dark), useMaterial3: true),
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
  bool _voiceRunning = false;
  bool _ttsSpeaking = false;
  bool _voiceStarting = false;
  String _status = 'Запуск JARVIS…';
  String _streamText = '';
  String _heardText = '';
  JarvisVisualState _visualState = JarvisVisualState.idle;
  bool get _android => Platform.isAndroid;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _android ? _initAndroid() : _connectDesktop();
    });
  }

  bool _looksLikeOpenRouterKey(String value) {
    final key = value.trim();
    return RegExp(r'^sk-or-v1-[A-Za-z0-9_-]{20,}$').hasMatch(key);
  }

  Future<void> _initVoice() async {
    if (!_android || _voiceReady) return;
    try {
      final available = await _speech.initialize(
        onStatus: (status) {
          debugPrint('JARVIS speech status: $status');
          if (!mounted) return;
          if (status == 'notListening' && _voiceRunning && !_ttsSpeaking && !_busy) {
            _scheduleVoiceRestart();
          }
        },
        onError: (error) {
          debugPrint('JARVIS speech error: $error');
          if (mounted && !_ttsSpeaking) setState(() => _status = 'Микрофон: ${error.errorMsg}');
          if (_voiceRunning && !_ttsSpeaking) _scheduleVoiceRestart();
        },
        debugLogging: false,
      );
      if (!available) throw StateError('Распознавание речи недоступно на устройстве');
      await _tts.setLanguage('ru-RU');
      await _tts.setSpeechRate(0.48);
      await _tts.setVolume(1.0);
      await _tts.setPitch(1.0);
      _tts.setStartHandler(() {
        _ttsSpeaking = true;
        if (mounted) _setVisual(JarvisVisualState.speaking);
      });
      _tts.setCompletionHandler(() {
        _ttsSpeaking = false;
        if (mounted) _returnToIdle(const Duration(milliseconds: 250));
        if (_voiceRunning) _scheduleVoiceRestart(const Duration(milliseconds: 350));
      });
      _tts.setCancelHandler(() {
        _ttsSpeaking = false;
        if (_voiceRunning) _scheduleVoiceRestart(const Duration(milliseconds: 350));
      });
      _voiceReady = true;
      if (mounted) setState(() => _status = 'Голос готов · скажите «Джарвис»');
    } catch (e) {
      _voiceReady = false;
      if (mounted) setState(() => _status = 'Голос недоступен: $e');
      _setVisual(JarvisVisualState.error);
    }
  }

  Future<void> _startVoiceLoop() async {
    if (!_android || !_voiceReady || _voiceStarting || _ttsSpeaking || _busy) return;
    _voiceStarting = true;
    try {
      await _speech.stop();
      await _speech.listen(
        onResult: _onSpeechResult,
        listenFor: const Duration(minutes: 1),
        pauseFor: const Duration(seconds: 4),
        partialResults: true,
        cancelOnError: false,
        listenMode: stt.ListenMode.dictation,
        localeId: 'ru_RU',
      );
      _voiceRunning = true;
      if (mounted) {
        setState(() => _status = _heardText.isEmpty ? 'Слушаю · жду «Джарвис»' : 'Слушаю…');
        _setVisual(JarvisVisualState.listening);
      }
    } catch (e) {
      _voiceRunning = false;
      if (mounted) setState(() => _status = 'Ошибка микрофона: $e');
      _scheduleVoiceRestart(const Duration(seconds: 2));
    } finally {
      _voiceStarting = false;
    }
  }

  void _scheduleVoiceRestart([Duration delay = const Duration(milliseconds: 500)]) {
    if (!_android || !_voiceRunning || _ttsSpeaking || _busy) return;
    _voiceRestartTimer?.cancel();
    _voiceRestartTimer = Timer(delay, () {
      if (mounted && _voiceRunning && !_ttsSpeaking && !_busy) _startVoiceLoop();
    });
  }

  String? _extractWakeCommand(String text) {
    final normalized = text.toLowerCase().replaceAll(RegExp(r'[,.!?;:]'), ' ').replaceAll(RegExp(r'\s+'), ' ').trim();
    final match = RegExp(r'\bджарвис\b').firstMatch(normalized);
    if (match == null) return null;
    final command = normalized.substring(match.end).trim();
    return command.isEmpty ? '' : command;
  }

  void _onSpeechResult(stt.SpeechRecognitionResult result) {
    final text = result.recognizedWords.trim();
    if (text.isEmpty || !mounted) return;
    setState(() {
      _heardText = text;
      _status = 'Слышу: $text';
    });
    _setVisual(JarvisVisualState.listening);
    final command = _extractWakeCommand(text);
    if (command == null) return;
    _voiceRestartTimer?.cancel();
    if (command.isEmpty) {
      _ttsSpeaking = true;
      _speech.stop();
      _tts.speak('Да, слушаю.');
      _ttsSpeaking = false;
      _scheduleVoiceRestart(const Duration(seconds: 1));
      return;
    }
    _speech.stop();
    _send(command, speakReply: true);
  }

  Future<void> _speak(String text) async {
    if (!_android || text.trim().isEmpty || !_voiceReady) return;
    try {
      _ttsSpeaking = true;
      await _tts.stop();
      _setVisual(JarvisVisualState.speaking);
      await _tts.speak(text.trim());
    } catch (e) {
      _ttsSpeaking = false;
      if (mounted) setState(() => _status = 'TTS ошибка: $e');
      _setVisual(JarvisVisualState.error);
    }
  }

  Future<void> _initAndroid() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      _endpoint.text = prefs.getString('endpoint') ?? 'https://openrouter.ai/api/v1';
      final savedModel = prefs.getString('model')?.trim() ?? '';
      if (savedModel.isEmpty || savedModel == 'openrouter/free' || savedModel == 'deepseek/deepseek-v4-flash:free') {
        _model.text = kFreeModel;
      } else {
        _model.text = savedModel;
      }
      final savedKey = prefs.getString('api_key')?.trim() ?? '';
      _apiKey.text = _looksLikeOpenRouterKey(savedKey) ? savedKey : '';
      if (!_apiKey.text.isNotEmpty && savedKey.isNotEmpty) await prefs.remove('api_key');
      await _initVoice();
      if (!mounted) return;
      if (_apiKey.text.isEmpty) {
        setState(() => _status = 'Введите API key OpenRouter в Настройках');
      } else {
        await _connectAndroid();
      }
    } catch (e) {
      if (mounted) {
        setState(() => _status = 'JARVIS запущен · ошибка: $e');
        _setVisual(JarvisVisualState.error);
      }
    }
  }

  Future<void> _saveSettings() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('endpoint', _endpoint.text.trim());
    await prefs.setString('model', _model.text.trim());
    await prefs.setString('api_key', _apiKey.text.trim());
  }

  Future<void> _connectAndroid() async {
    final endpoint = _endpoint.text.trim();
    final model = _model.text.trim();
    final key = _apiKey.text.trim();
    if (endpoint.isEmpty || key.isEmpty) {
      if (mounted) setState(() => _status = 'Введите API key OpenRouter в Настройках');
      _setVisual(JarvisVisualState.error);
      return;
    }
    if (!_looksLikeOpenRouterKey(key)) {
      if (mounted) setState(() => _status = 'Неверный API key: нужен ключ sk-or-v1-…');
      _setVisual(JarvisVisualState.error);
      return;
    }
    try {
      await _saveSettings();
      if (mounted) setState(() => _status = 'Подключение к OpenRouter…');
      _setVisual(JarvisVisualState.thinking);
      await _jarvis?.dispose();
      _jarvis = await JarvisIpc.connectAi(endpoint, apiKey: key, model: model);
      await _finishConnect();
    } catch (e) {
      if (mounted) setState(() => _status = 'Ошибка AI: $e');
      _setVisual(JarvisVisualState.error);
    }
  }

  Future<void> _connectDesktop() async {
    try {
      final dir = File(Platform.resolvedExecutable).parent.path;
      final exe = '$dir${Platform.pathSeparator}jarvis.exe';
      _jarvis = await (File(exe).existsSync() ? JarvisIpc.spawn(exe) : JarvisIpc.spawn('python', ['-m', 'agent', '--ipc']));
      await _finishConnect();
    } catch (e) {
      if (mounted) {
        setState(() => _status = 'Агент не запущен: $e');
        _setVisual(JarvisVisualState.error);
      }
    }
  }

  Future<void> _finishConnect() async {
    if (_jarvis == null) return;
    final tools = _android ? const <String>[] : await _jarvis!.listTools();
    if (!mounted) return;
    setState(() => _status = _android ? 'OpenRouter · Qwen Free · JARVIS активен' : 'JARVIS подключён · инструментов: ${tools.length}');
    _setVisual(JarvisVisualState.confirmation);
    _returnToIdle(const Duration(milliseconds: 1100));
    await _partialSub?.cancel();
    _partialSub = _jarvis!.partials().listen((text) {
      if (mounted) setState(() {
        _streamText = text;
        if (text.isNotEmpty) _visualState = JarvisVisualState.speaking;
      });
    });
    if (_android && _voiceReady) {
      _voiceRunning = true;
      _startVoiceLoop();
    }
  }

  Future<void> _settings() async {
    if (!_android) return;
    await _speech.stop();
    _voiceRunning = false;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('JARVIS — настройки'),
        content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: _endpoint, keyboardType: TextInputType.url, decoration: const InputDecoration(labelText: 'Endpoint', hintText: 'https://openrouter.ai/api/v1')),
          TextField(controller: _model, decoration: const InputDecoration(labelText: 'Модель', hintText: kFreeModel)),
          Align(alignment: Alignment.centerLeft, child: TextButton.icon(onPressed: () => setState(() => _model.text = kFreeModel), icon: const Icon(Icons.auto_awesome), label: const Text('Выбрать бесплатную модель'))),
          TextField(controller: _apiKey, obscureText: true, decoration: const InputDecoration(labelText: 'API key', hintText: 'sk-or-v1-...')),
          const Text('Голос: автоматическое ожидание команды «Джарвис», распознавание русского и ответ голосом.', style: TextStyle(fontSize: 12)),
        ])),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Отмена')),
          FilledButton(onPressed: () { Navigator.pop(ctx); _connectAndroid(); }, child: const Text('Сохранить и подключить')),
        ],
      ),
    );
    if (mounted && _jarvis != null && _voiceReady) {
      _voiceRunning = true;
      _startVoiceLoop();
    }
  }

  Future<void> _send(String text, {bool speakReply = false}) async {
    text = text.trim();
    if (text.isEmpty || _jarvis == null || _busy) return;
    _input.clear();
    setState(() {
      _messages.add(_Msg(text, isUser: true));
      _busy = true;
      _streamText = '';
      _visualState = JarvisVisualState.thinking;
      _status = 'Думаю…';
    });
    try {
      final reply = await _jarvis!.sendMessage(text);
      if (mounted) {
        setState(() {
          _messages.add(_Msg(reply.text, isUser: false));
          _visualState = JarvisVisualState.speaking;
          _status = 'Готов';
        });
      }
      if (speakReply) await _speak(reply.text);
      _returnToIdle(const Duration(milliseconds: 800));
    } catch (e) {
      if (mounted) {
        final errorText = 'Ошибка: $e';
        setState(() => _messages.add(_Msg(errorText, isUser: false)));
        _setVisual(JarvisVisualState.error);
        setState(() => _status = 'Ошибка AI');
      }
      if (speakReply) await _speak('Произошла ошибка. Проверьте подключение к OpenRouter.');
    } finally {
      if (mounted) setState(() { _busy = false; _streamText = ''; });
      if (_voiceRunning && !_ttsSpeaking) _scheduleVoiceRestart(const Duration(milliseconds: 500));
    }
  }

  void _setVisual(JarvisVisualState state) {
    if (!mounted) return;
    setState(() => _visualState = state);
    _visualTimer?.cancel();
  }

  void _returnToIdle(Duration delay) {
    _visualTimer?.cancel();
    _visualTimer = Timer(delay, () {
      if (mounted) setState(() => _visualState = JarvisVisualState.idle);
    });
  }

  @override
  void dispose() {
    _partialSub?.cancel();
    _visualTimer?.cancel();
    _voiceRestartTimer?.cancel();
    _speech.stop();
    _tts.stop();
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
      appBar: AppBar(title: const Text('JARVIS'), actions: [if (_android) IconButton(onPressed: _settings, icon: const Icon(Icons.settings))]),
      body: Column(children: [
        Expanded(child: ListView.builder(controller: _scroll, padding: const EdgeInsets.all(16), itemCount: _messages.length + (_streamText.isNotEmpty ? 1 : 0), itemBuilder: (context, index) {
          if (_streamText.isNotEmpty && index == _messages.length) return Align(alignment: Alignment.centerLeft, child: Text(_streamText));
          final m = _messages[index];
          return Align(alignment: m.isUser ? Alignment.centerRight : Alignment.centerLeft, child: Container(margin: const EdgeInsets.only(bottom: 10), padding: const EdgeInsets.all(12), decoration: BoxDecoration(color: m.isUser ? kPanel : kBg, borderRadius: BorderRadius.circular(12), border: Border.all(color: kCyan.withValues(alpha: 0.25))), child: Text(m.text)));
        })),
        if (_android && _heardText.isNotEmpty) Padding(padding: const EdgeInsets.symmetric(horizontal: 12), child: Text('🎙 $_heardText', maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 11))),
        Padding(padding: const EdgeInsets.fromLTRB(12, 4, 12, 12), child: Row(children: [
          Expanded(child: TextField(controller: _input, textInputAction: TextInputAction.send, onSubmitted: _send, decoration: const InputDecoration(hintText: 'Спросите JARVIS…'))),
          IconButton(onPressed: _busy ? null : () => _send(_input.text), icon: const Icon(Icons.send)),
        ])),
        Padding(padding: const EdgeInsets.only(bottom: 10), child: Text(_status, style: const TextStyle(fontSize: 12))),
      ]),
    );
  }
}
