import 'dart:async';
import 'dart:io';
import 'package:flutter/services.dart';
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

class _JarvisHomePageState extends State<JarvisHomePage> {
  JarvisIpc? _jarvis;
  final _input = TextEditingController();
  final _endpoint = TextEditingController();
  final _apiKey = TextEditingController();
  final _model = TextEditingController();
  final _fallbackEndpoint = TextEditingController();
  final _fallbackKey = TextEditingController();
  final _fallbackModel = TextEditingController();
  static const _platform = MethodChannel('com.dancorsoodessa.jarvis/timer');
  final _scroll = ScrollController();
  final _messages = <_Msg>[];
  final stt.SpeechToText _speech = stt.SpeechToText();
  final FlutterTts _tts = FlutterTts();
  StreamSubscription<String>? _partialSub;
  Timer? _visualTimer;
  Timer? _voiceRestartTimer;
  int _speechSession = 0;
  bool _busy = false;
  bool _voiceReady = false;
  bool _voiceRunning = false;
  bool _ttsSpeaking = false;
  bool _voiceStarting = false;
  bool _wakeArmed = false;
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

  Future<void> _initVoice() async {
    if (!_android || _voiceReady) return;
    try {
      // Voice startup is non-fatal: a broken native speech/TTS engine
      // must never prevent the main JARVIS UI from opening.
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
      try {
        await _tts.setLanguage('ru-RU');
        await _tts.setSpeechRate(0.48);
        await _tts.setVolume(1.0);
        await _tts.setPitch(1.0);
      } catch (e) {
        debugPrint('JARVIS TTS init warning: $e');
      }
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
        onResult: (result) => _onSpeechResult(result, _speechSession),
        listenFor: const Duration(minutes: 1),
        pauseFor: const Duration(seconds: 4),
        partialResults: true,
        cancelOnError: false,
        listenMode: stt.ListenMode.dictation,
        localeId: 'ru_RU',
      );
      _voiceRunning = true;
      if (mounted) {
        setState(() => _status = _wakeArmed ? 'Слушаю команду…' : 'Слушаю · жду «Джарвис»');
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

  Future<void> _onSpeechResult(dynamic result, int session) async {
    if (session != _speechSession) return;
    final text = result.recognizedWords?.toString().trim() ?? '';
    final isFinal = result.finalResult == true;
    if (text.isEmpty || !mounted) return;
    setState(() {
      _heardText = text;
      _status = _wakeArmed ? 'Слышу команду: $text' : 'Слышу: $text';
    });
    _setVisual(JarvisVisualState.listening);
    if (!isFinal) return;

    final wakeCommand = _extractWakeCommand(text);
    _voiceRestartTimer?.cancel();

    if (wakeCommand != null) {
      _speechSession++;
      if (wakeCommand.isEmpty) {
        _wakeArmed = true;
        await _speech.stop();
        await _speak('Да, слушаю.');
        return;
      }
      _wakeArmed = false;
      await _speech.stop();
      await _send(wakeCommand, speakReply: true);
      return;
    }

    if (_wakeArmed) {
      _speechSession++;
      _wakeArmed = false;
      await _speech.stop();
      await _send(text, speakReply: true);
    }
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
      _endpoint.text = prefs.getString('endpoint') ?? 'https://api.openai.com/v1';
      _model.text = prefs.getString('model')?.trim() ?? 'gpt-4o-mini';
      _apiKey.text = prefs.getString('api_key')?.trim() ?? '';
      _fallbackEndpoint.text = prefs.getString('fallback_endpoint')?.trim() ?? 'https://openrouter.ai/api/v1';
      _fallbackKey.text = prefs.getString('fallback_key')?.trim() ?? '';
      _fallbackModel.text = prefs.getString('fallback_model')?.trim() ?? '';
      // Do not block application startup on native voice services.
      await Future<void>.delayed(const Duration(milliseconds: 300));
      if (mounted) await _initVoice();
      if (!mounted) return;
      if (_apiKey.text.isEmpty) {
        setState(() => _status = 'Введите API key в Настройках');
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
    await prefs.setString('fallback_endpoint', _fallbackEndpoint.text.trim());
    await prefs.setString('fallback_key', _fallbackKey.text.trim());
    await prefs.setString('fallback_model', _fallbackModel.text.trim());
  }

  Future<void> _connectAndroid() async {
    final endpoint = _endpoint.text.trim();
    final model = _model.text.trim();
    final key = _apiKey.text.trim();
    if (endpoint.isEmpty || key.isEmpty) {
      if (mounted) setState(() => _status = 'Введите AI URL и API key в Настройках');
      _setVisual(JarvisVisualState.error);
      return;
    }
    try {
      await _saveSettings();
      if (mounted) setState(() => _status = 'Проверяю основной и резервный AI…');
      _setVisual(JarvisVisualState.thinking);
      await _jarvis?.dispose();
      _jarvis = await JarvisIpc.connectAi(endpoint, apiKey: key, model: model, fallbackUrl: _fallbackEndpoint.text.trim(), fallbackKey: _fallbackKey.text.trim(), fallbackModel: _fallbackModel.text.trim());
      await _jarvis!.checkConnection();
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
    setState(() => _status = _android ? 'AI подключён · JARVIS активен' : 'JARVIS подключён · инструментов: ${tools.length}');
    _setVisual(JarvisVisualState.confirmation);
    _returnToIdle(const Duration(milliseconds: 1100));
    await _partialSub?.cancel();
    _partialSub = _jarvis!.partials().listen((text) {
      if (mounted) setState(() {
        _streamText = text;
        if (text.isNotEmpty) _visualState = JarvisVisualState.speaking;
      });
    });
    if (_android && _voiceReady && mounted) {
      _voiceRunning = true;
      Future<void>.delayed(const Duration(milliseconds: 700), () {
        if (mounted && _voiceRunning && !_busy && !_ttsSpeaking) {
          _startVoiceLoop();
        }
      });
    }
  }

  Future<void> _settings() async {
    if (!_android) return;
    _speechSession++;
    await _speech.stop();
    _voiceRunning = false;
    _wakeArmed = false;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('JARVIS — настройки'),
        content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Align(alignment: Alignment.centerLeft, child: Text('Основной AI', style: TextStyle(fontWeight: FontWeight.bold))),
          TextField(controller: _endpoint, keyboardType: TextInputType.url, decoration: const InputDecoration(labelText: 'AI URL', hintText: 'https://api.openai.com/v1')),
          TextField(controller: _apiKey, obscureText: true, decoration: const InputDecoration(labelText: 'API Key')),
          TextField(controller: _model, decoration: const InputDecoration(labelText: 'Model', hintText: 'gpt-4o-mini')),
          const SizedBox(height: 12),
          const Align(alignment: Alignment.centerLeft, child: Text('Резервный AI · при 429/5xx/сбое', style: TextStyle(fontWeight: FontWeight.bold))),
          TextField(controller: _fallbackEndpoint, keyboardType: TextInputType.url, decoration: const InputDecoration(labelText: 'Резервный AI URL')),
          TextField(controller: _fallbackKey, obscureText: true, decoration: const InputDecoration(labelText: 'Резервный API Key')),
          TextField(controller: _fallbackModel, decoration: const InputDecoration(labelText: 'Резервная Model')),
          const SizedBox(height: 8),
          const Text('Голос: автоматическое ожидание «Джарвис».', style: TextStyle(fontSize: 12)),
        ])),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Отмена')),
          FilledButton(onPressed: () { Navigator.pop(ctx); _connectAndroid(); }, child: const Text('Сохранить и подключить')),
        ],
      ),
    );
    if (mounted && _jarvis != null && _voiceReady) {
      _voiceRunning = true;
      _wakeArmed = false;
      _startVoiceLoop();
    }
  }

  Future<void> _send(String text, {bool speakReply = false}) async {
    text = text.trim();
    if (text.isEmpty || _jarvis == null || _busy) return;
    if (await _handleTimer(text)) { _input.clear(); return; }
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
        setState(() => _status = 'Ошибка AI: $e');
      }
      if (speakReply) await _speak('Произошла ошибка. Проверьте подключение к AI.');
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

  Future<Duration?> _parseTimer(String text) async {
    final s = text.toLowerCase();
    final m = RegExp(r'(?:таймер|напомни|напоминание)\s*(?:на|через)?\s*(\d+(?:[.,]\d+)?)\s*(сек|секунд(?:у|ы)?|s|мин|минут(?:у|ы)?|m|ч|час(?:а|ов)?|h)').firstMatch(s);
    if (m == null) return null;
    final value = double.tryParse(m.group(1)!.replaceAll(',', '.'));
    if (value == null || value <= 0) return null;
    final u = m.group(2)!;
    if (u == 's' || u.startsWith('сек')) return Duration(milliseconds: (value * 1000).round());
    if (u == 'm' || u.startsWith('мин')) return Duration(milliseconds: (value * 60000).round());
    return Duration(milliseconds: (value * 3600000).round());
  }

  Future<bool> _handleTimer(String text) async {
    if (!_android) return false;
    final d = await _parseTimer(text);
    if (d == null) return false;
    try {
      await _platform.invokeMethod('scheduleTimer', {'delayMs': d.inMilliseconds, 'label': text});
      final mins = d.inMinutes;
      final reply = mins > 0 ? 'Таймер установлен на $mins минут.' : 'Таймер установлен на ${d.inSeconds} секунд.';
      if (mounted) setState(() => _messages.add(_Msg(reply, isUser: false)));
      await _speak(reply);
    } catch (e) {
      if (mounted) setState(() => _status = 'Ошибка таймера: $e');
    }
    return true;
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
    _fallbackEndpoint.dispose();
    _fallbackKey.dispose();
    _fallbackModel.dispose();
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
          return Align(alignment: m.isUser ? Alignment.centerRight : Alignment.centerLeft, child: Container(margin: const EdgeInsets.only(bottom: 10), padding: const EdgeInsets.all(12), decoration: BoxDecoration(color: m.isUser ? kPanel : kBg, borderRadius: BorderRadius.circular(12), border: Border.all(color: kCyan.withValues(alpha: 0.25))), child: Row(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [Flexible(child: SelectableText(m.text)), if (!m.isUser) IconButton(onPressed: () { Clipboard.setData(ClipboardData(text: m.text)); setState(() => _status = 'Текст скопирован'); }, icon: const Icon(Icons.copy, size: 18))])));
        })),
        if (_android && _heardText.isNotEmpty) Padding(padding: const EdgeInsets.symmetric(horizontal: 12), child: Text('🎙 $_heardText', maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 11))),
        Padding(padding: const EdgeInsets.fromLTRB(12, 4, 12, 12), child: Row(children: [
          Expanded(child: TextField(controller: _input, minLines: 2, maxLines: 5, textInputAction: TextInputAction.newline, onSubmitted: _send, decoration: const InputDecoration(hintText: 'Введите команду или вопрос…', border: OutlineInputBorder()))),
          IconButton(onPressed: _busy ? null : () => _send(_input.text), icon: const Icon(Icons.send)),
        ])),
        Padding(padding: const EdgeInsets.only(bottom: 10), child: Text(_status, style: const TextStyle(fontSize: 12))),
      ]),
    );
  }
}

class JarvisHomePage extends StatefulWidget {
  const JarvisHomePage({super.key});
  @override
  State<JarvisHomePage> createState() => _JarvisHomePageState();
}
