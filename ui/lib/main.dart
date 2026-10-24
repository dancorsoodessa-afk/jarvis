import 'dart:async';
import 'dart:io';
import 'package:flutter/services.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:flutter_tts/flutter_tts.dart';
import 'package:permission_handler/permission_handler.dart';
import 'jarvis_client.dart';
import 'jarvis_reactor.dart';

const kCyan = Color(0xFF37D5EE);
const kBg = Color(0xFF05080F);
const kPanel = Color(0xFF0D1622);
const kFreePrimaryUrl = 'https://generativelanguage.googleapis.com/v1beta/openai';
const kFreePrimaryModel = 'gemini-3.8-flash';
const kFreeFallbackUrl = '';
const kFreeFallbackModel = '';

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
  double _voiceLevel = 0.0;
  int _voiceRestartAttempts = 0;
  bool _wakeArmed = false;
  String _status = 'Запуск JARVIS…';
  String _streamText = '';
  String _heardText = '';
  JarvisVisualState _visualState = JarvisVisualState.idle;
  bool get _android => Platform.isAndroid;

  @override
  void initState() {
    super.initState();
    // Install TTS callbacks before any timer or voice action can call _speak.
    // Otherwise a timer response before microphone initialization can leave
    // _ttsSpeaking stuck true because no completion handler resets it.
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
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _android ? _initAndroid() : _connectDesktop();
    });
  }

  Future<void> _initVoice() async {
    if (!_android || _voiceReady) return;
    try {
      final mic = await Permission.microphone.request();
      if (!mic.isGranted) {
        if (mounted) {
          setState(() {
            _status = mic.isPermanentlyDenied
                ? 'Микрофон заблокирован. Разрешите микрофон в настройках Android.'
                : 'Нужно разрешение на микрофон.';
          });
        }
        return;
      }
      // Voice startup is non-fatal: a broken native speech/TTS engine
      // must never prevent the main JARVIS UI from opening.
      final available = await _speech.initialize(
        onStatus: (status) {
          debugPrint('JARVIS speech status: $status');
          if (!mounted) return;
          if (status == 'notListening' && _voiceRunning && !_voiceStarting && !_ttsSpeaking && !_busy) {
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
    // Lock before the first await so concurrent callbacks cannot start two listeners.
    _voiceStarting = true;
    try {
      final mic = await Permission.microphone.status;
      if (!mic.isGranted) {
        _voiceRunning = false;
        if (mounted) setState(() => _status = 'Нет разрешения на микрофон');
        return;
      }
      final session = _speechSession;
      await _speech.stop();
      await _speech.listen(
        onResult: (result) => _onSpeechResult(result, session),
        listenOptions: stt.SpeechListenOptions(
          listenFor: const Duration(minutes: 1),
          pauseFor: const Duration(seconds: 4),
          partialResults: true,
          cancelOnError: false,
          listenMode: stt.ListenMode.dictation,
          localeId: 'ru_RU',
        ),
        onSoundLevelChange: (level) {
          if (!mounted) return;
          final activity = ((level + 2.0) / 12.0).clamp(0.0, 1.0).toDouble();
          if ((_voiceLevel - activity).abs() >= 0.04) {
            setState(() => _voiceLevel = activity);
          }
        },
      );
      _voiceRestartAttempts = 0;
      _voiceRunning = true;
      if (mounted) {
        setState(() => _status = _wakeArmed ? 'Слушаю команду…' : 'Слушаю · жду «Джарвис»');
        _setVisual(JarvisVisualState.listening);
      }
    } catch (e) {
      final canRetry = _voiceRestartAttempts < 3;
      _voiceRunning = canRetry;
      if (canRetry) {
        _voiceRestartAttempts++;
      }
      if (mounted) {
        setState(() {
          _status = canRetry
              ? 'Ошибка микрофона, повтор $_voiceRestartAttempts/3: $e'
              : 'Микрофон остановлен после 3 неудачных попыток: $e';
        });
      }
      if (canRetry) _scheduleVoiceRestart(const Duration(seconds: 2));
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
    final match = RegExp(r'(^|[^a-zа-яё0-9])(?:джарвис|jarvis)(?=$|[^a-zа-яё0-9])').firstMatch(normalized);
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
      if (isFinal) _voiceLevel = 0.0;
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
    if (!_android || text.trim().isEmpty) return;
    try {
      await _tts.stop();
      // stop() may invoke the cancel handler; set speaking only after it ends
      // so a queued microphone restart cannot race the new utterance.
      _ttsSpeaking = true;
      if (!_voiceReady) {
        await _tts.setLanguage('ru-RU');
        await _tts.setSpeechRate(0.48);
        await _tts.setVolume(1.0);
        await _tts.setPitch(1.0);
      }
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
      final storedEndpoint = prefs.getString('endpoint')?.trim() ?? '';
      final storedModel = prefs.getString('model')?.trim() ?? '';
      final storedKey = prefs.getString('api_key')?.trim() ?? '';
      // JARVIS Android uses the official Gemini OpenAI-compatible endpoint.
      final usingOldProvider = storedEndpoint != kFreePrimaryUrl;
      if (usingOldProvider) {
        _endpoint.text = kFreePrimaryUrl;
        _model.text = kFreePrimaryModel;
        // Never reuse a key from a different provider.
        _apiKey.text = '';
      } else {
        _endpoint.text = storedEndpoint;
        _model.text = storedModel.isEmpty ? kFreePrimaryModel : storedModel;
        _apiKey.text = storedKey;
      }

      _fallbackEndpoint.text = '';
      _fallbackKey.text = prefs.getString('fallback_key')?.trim() ?? '';
      _fallbackModel.text = '';
      // Do not initialize native microphone/speech services during startup.
      // Voice is initialized only after the main UI is visible, preventing
      // device-specific native speech-service crashes from closing JARVIS.
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
    _endpoint.text = kFreePrimaryUrl;
    await prefs.setString('endpoint', kFreePrimaryUrl);
    await prefs.setString('model', _model.text.trim());
    await prefs.setString('api_key', _apiKey.text.trim());
    await prefs.setString('fallback_endpoint', '');
    await prefs.setString('fallback_key', '');
    await prefs.setString('fallback_model', '');
  }

  Future<void> _connectAndroid() async {
    const endpoint = kFreePrimaryUrl;
    final model = _model.text.trim();
    final key = _apiKey.text.trim();
    if (endpoint.isEmpty || key.isEmpty) {
      if (mounted) setState(() => _status = 'Введите AI URL и API key в Настройках');
      _setVisual(JarvisVisualState.error);
      return;
    }
    try {
      await _saveSettings();
      if (mounted) setState(() => _status = 'Проверяю ответ Gemini…');
      _setVisual(JarvisVisualState.thinking);
      await _jarvis?.dispose();
      _jarvis = await JarvisIpc.connectAi(endpoint, apiKey: key, model: model, fallbackUrl: '', fallbackKey: '', fallbackModel: '');
      await _jarvis!.checkConnection();
      await _finishConnect();
      // Start hands-free voice only after the AI connection and first frame are ready.
      // Native speech service failures remain non-fatal inside _initVoice().
      await _initVoice();
      if (_voiceReady && mounted) {
        _voiceRunning = true;
        await _startVoiceLoop();
      }
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
    _speechSession++;
    await _speech.stop();
    if (!mounted) return;
    _voiceRunning = false;
    _wakeArmed = false;
    final shouldConnect = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('JARVIS — настройки'),
        content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Align(alignment: Alignment.centerLeft, child: Text('Google Gemini API', style: TextStyle(fontWeight: FontWeight.bold))),
          TextField(controller: _endpoint, readOnly: true, decoration: const InputDecoration(labelText: 'AI URL · Gemini', hintText: 'https://generativelanguage.googleapis.com/v1beta/openai')),
          TextField(controller: _apiKey, obscureText: true, decoration: const InputDecoration(labelText: 'Gemini API Key')),
          TextField(controller: _model, decoration: const InputDecoration(labelText: 'Модель Gemini', hintText: 'gemini-3.8-flash')),
          const SizedBox(height: 8),
          const Text(
            'Подключение выполняется через Google Gemini API. Создайте ключ в Google AI Studio; бесплатный тариф имеет ограничения.',
            style: TextStyle(fontSize: 12),
          ),
          const SizedBox(height: 4),
          const Text('Голос: автоматическое ожидание «Джарвис».', style: TextStyle(fontSize: 12)),
        ])),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Отмена')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Сохранить и подключить')),
        ],
      ),
    );
    if (!mounted) return;
    if (shouldConnect == true) {
      await _connectAndroid();
    } else if (_jarvis != null && _voiceReady) {
      // Resume the existing voice session after dismissing settings.
      _voiceRunning = true;
      _wakeArmed = false;
      await _startVoiceLoop();
    }
  }

  Future<void> _send(String text, {bool speakReply = false}) async {
    text = text.trim();
    if (text.isEmpty || _busy) return;
    // Local Android timers must work even when cloud AI is not configured
    // or temporarily offline; handle them before requiring an AI connection.
    if (await _handleTimer(text)) { _input.clear(); return; }
    if (_jarvis == null) {
      const message = 'AI не подключён. Откройте настройки и подключите Gemini.';
      if (mounted) {
        setState(() {
          _status = message;
          _messages.add(_Msg(message, isUser: false));
        });
        _setVisual(JarvisVisualState.error);
      }
      if (speakReply) await _speak(message);
      return;
    }
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
    final m = RegExp(r'(?:таймер|напомни|напоминание)\s*(?:мне\s*)?(?:на|через)?\s*(\d+(?:[.,]\d+)?)\s*(сек|секунд(?:у|ы)?|s|мин|минут(?:у|ы)?|m|ч|час(?:а|ов)?|h|дн(?:я|ей)?|день)').firstMatch(s);
    if (m == null) return null;
    final value = double.tryParse(m.group(1)!.replaceAll(',', '.'));
    if (value == null || !value.isFinite || value <= 0) return null;
    final u = m.group(2)!;
    final multiplier = u == 's' || u.startsWith('сек')
        ? 1000.0
        : u == 'm' || u.startsWith('мин')
            ? 60000.0
            : u == 'h' || u == 'ч' || u.startsWith('час')
                ? 3600000.0
                : 86400000.0;
    final milliseconds = value * multiplier;
    // Bound timers to one year and avoid overflowing Duration/AlarmManager values.
    if (!milliseconds.isFinite || milliseconds > const Duration(days: 365).inMilliseconds) return null;
    return Duration(milliseconds: milliseconds.round());
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

  Color get _visualColor => switch (_visualState) {
    JarvisVisualState.idle => kCyan,
    JarvisVisualState.listening => const Color(0xFF48F0B4),
    JarvisVisualState.thinking => const Color(0xFF8B7CFF),
    JarvisVisualState.speaking => const Color(0xFF39C6FF),
    JarvisVisualState.confirmation => const Color(0xFF72F5CE),
    JarvisVisualState.error => const Color(0xFFFF526B),
    JarvisVisualState.exiting => const Color(0xFF718096),
  };

  String get _visualLabel => switch (_visualState) {
    JarvisVisualState.idle => 'ГОТОВ К РАБОТЕ',
    JarvisVisualState.listening => 'СЛУШАЮ',
    JarvisVisualState.thinking => 'ОБРАБАТЫВАЮ ЗАПРОС',
    JarvisVisualState.speaking => 'ОТВЕЧАЮ',
    JarvisVisualState.confirmation => 'ПОДКЛЮЧЕНО',
    JarvisVisualState.error => 'ТРЕБУЕТСЯ ПРОВЕРКА',
    JarvisVisualState.exiting => 'ЗАВЕРШЕНИЕ',
  };

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('JARVIS XXX', style: TextStyle(letterSpacing: 2, fontWeight: FontWeight.w600)),
        actions: [if (_android) IconButton(tooltip: 'Настройки Gemini', onPressed: _settings, icon: const Icon(Icons.tune))],
      ),
      body: SafeArea(
        child: Column(children: [
          SizedBox(
            height: 272,
            width: double.infinity,
            child: Stack(alignment: Alignment.center, children: [
              Positioned.fill(child: JarvisReactor(color: _visualColor, state: _visualState, activity: _voiceLevel)),
              Positioned(
                bottom: 12,
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  Text(_visualLabel, style: TextStyle(color: _visualColor, fontSize: 11, letterSpacing: 2.2, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 5),
                  SizedBox(width: MediaQuery.sizeOf(context).width * 0.78,
                    child: Text(_status, maxLines: 2, overflow: TextOverflow.ellipsis, textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.white.withValues(alpha: 0.72), fontSize: 12))),
                ]),
              ),
            ]),
          ),
          const Divider(height: 1, color: Color(0xFF182736)),
          Expanded(
            child: _messages.isEmpty && _streamText.isEmpty
              ? Center(child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    Icon(Icons.graphic_eq, color: _visualColor, size: 30),
                    const SizedBox(height: 12),
                    const Text('Система готова', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w500)),
                    const SizedBox(height: 6),
                    Text('Введите запрос или нажмите микрофон и скажите «Джарвис».',
                      textAlign: TextAlign.center, style: TextStyle(color: Colors.white.withValues(alpha: 0.58), fontSize: 13)),
                  ]),
                ))
              : ListView.builder(
                  controller: _scroll,
                  padding: const EdgeInsets.fromLTRB(14, 14, 14, 8),
                  itemCount: _messages.length + (_streamText.isNotEmpty ? 1 : 0),
                  itemBuilder: (context, index) {
                    if (_streamText.isNotEmpty && index == _messages.length) {
                      return Align(alignment: Alignment.centerLeft, child: _messageBubble(_streamText, false));
                    }
                    final m = _messages[index];
                    return Align(alignment: m.isUser ? Alignment.centerRight : Alignment.centerLeft,
                      child: _messageBubble(m.text, m.isUser));
                  },
                ),
          ),
          if (_android && _heardText.isNotEmpty)
            Padding(padding: const EdgeInsets.fromLTRB(14, 0, 14, 6),
              child: Row(children: [
                Icon(Icons.graphic_eq, color: _visualColor, size: 16),
                const SizedBox(width: 6),
                Expanded(child: Text(_heardText, maxLines: 1, overflow: TextOverflow.ellipsis,
                  style: TextStyle(color: Colors.white.withValues(alpha: 0.62), fontSize: 11))),
              ])),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 8, 8),
            child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Expanded(child: TextField(
                controller: _input, minLines: 1, maxLines: 4,
                textInputAction: TextInputAction.newline,
                onSubmitted: _send,
                decoration: InputDecoration(
                  hintText: 'Сообщение JARVIS…',
                  filled: true, fillColor: kPanel,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide.none),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 15, vertical: 12),
                ),
              )),
              const SizedBox(width: 6),
              IconButton.filled(
                tooltip: 'Отправить',
                onPressed: _busy ? null : () => _send(_input.text),
                icon: const Icon(Icons.arrow_upward),
              ),
              if (_android)
                IconButton(
                  tooltip: _voiceRunning ? 'Остановить микрофон' : 'Включить голос',
                  onPressed: _busy ? null : () async {
                    if (_voiceRunning) {
                      _speechSession++;
                      _voiceRunning = false;
                      _voiceLevel = 0.0;
                      _voiceRestartTimer?.cancel();
                      await _speech.stop();
                      if (mounted) setState(() { _status = 'Голос остановлен'; _visualState = JarvisVisualState.idle; });
                    } else {
                      if (!_voiceReady) await _initVoice();
                      if (_voiceReady && mounted) {
                        _voiceRunning = true;
                        await _startVoiceLoop();
                      }
                    }
                  },
                  icon: Icon(_voiceRunning ? Icons.mic : Icons.mic_none, color: _voiceRunning ? _visualColor : null),
                ),
            ]),
          ),
        ]),
      ),
    );
  }

  Widget _messageBubble(String text, bool isUser) => Container(
    margin: const EdgeInsets.only(bottom: 10),
    padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 11),
    constraints: const BoxConstraints(maxWidth: 620),
    decoration: BoxDecoration(
      color: isUser ? const Color(0xFF102632) : kPanel,
      borderRadius: BorderRadius.circular(15),
      border: Border.all(color: (isUser ? kCyan : const Color(0xFF344454)).withValues(alpha: 0.32)),
    ),
    child: SelectableText(text, style: const TextStyle(fontSize: 14, height: 1.4)),
  );
}

class JarvisHomePage extends StatefulWidget {
  const JarvisHomePage({super.key});
  @override
  State<JarvisHomePage> createState() => _JarvisHomePageState();
}
