import 'dart:async';
import 'dart:io';
import 'dart:convert';
import 'package:flutter/services.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:flutter_tts/flutter_tts.dart';
import 'package:permission_handler/permission_handler.dart';
import 'jarvis_client.dart';
import 'jarvis_reactor.dart';

const kCyan = Color(0xFF37D5EE);
const kBg = Color(0xFF05080F);
const kPanel = Color(0xFF0D1622);
const kFreePrimaryUrl = 'https://generativelanguage.googleapis.com/v1beta/openai';
const kFreePrimaryModel = '';
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
  static const FlutterSecureStorage _secureStorage = FlutterSecureStorage();
  final _input = TextEditingController();
  final _endpoint = TextEditingController();
  final _apiKey = TextEditingController();
  final _model = TextEditingController();
  final _fallbackEndpoint = TextEditingController();
  final _fallbackKey = TextEditingController();
  final _fallbackModel = TextEditingController();
  static const _platform = MethodChannel('com.dancorsoodessa.jarvis/timer');
  static const _nativeTools = MethodChannel('jarvis.voice');
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
      final legacyKey = prefs.getString('api_key')?.trim() ?? '';
      var storedKey = await _secureStorage.read(key: 'api_key') ?? '';
      if (storedKey.isEmpty && legacyKey.isNotEmpty) {
        await _secureStorage.write(key: 'api_key', value: legacyKey);
        storedKey = legacyKey;
      }
      await prefs.remove('api_key');
      final legacyFallbackKey = prefs.getString('fallback_key')?.trim() ?? '';
      var storedFallbackKey = await _secureStorage.read(key: 'fallback_key') ?? '';
      if (storedFallbackKey.isEmpty && legacyFallbackKey.isNotEmpty) {
        await _secureStorage.write(key: 'fallback_key', value: legacyFallbackKey);
        storedFallbackKey = legacyFallbackKey;
      }
      await prefs.remove('fallback_key');
      // Preserve the user's configured OpenAI-compatible provider and key.
      // A stale model ID is the common cause of a "connected" UI with failed chat.
      _endpoint.text = storedEndpoint.isEmpty ? kFreePrimaryUrl : storedEndpoint;
      final googleEndpoint = Uri.tryParse(_endpoint.text)?.host.toLowerCase() ==
          'generativelanguage.googleapis.com';
      final staleCrossProviderModel = googleEndpoint &&
          storedModel.toLowerCase().startsWith('openrouter/');
      // Old versions could save OpenRouter model IDs under Gemini. Clear that
      // mismatch so the client can discover models allowed by this API key.
      _model.text = staleCrossProviderModel
          ? ''
          : (storedModel.isEmpty ? kFreePrimaryModel : storedModel);
      if (staleCrossProviderModel) await prefs.setString('model', '');
      _apiKey.text = storedKey;

      _fallbackEndpoint.text = prefs.getString('fallback_endpoint')?.trim() ?? '';
      _fallbackKey.text = storedFallbackKey.trim();
      _fallbackModel.text = prefs.getString('fallback_model')?.trim() ?? '';
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
    final endpoint = _endpoint.text.trim();
    if (endpoint.isEmpty) throw ArgumentError('Укажите адрес AI API');
    await prefs.setString('endpoint', endpoint);
    await prefs.setString('model', _model.text.trim().isEmpty ? kFreePrimaryModel : _model.text.trim());
    await _secureStorage.write(key: 'api_key', value: _apiKey.text.trim());
    await prefs.remove('api_key');
    await prefs.setString('fallback_endpoint', _fallbackEndpoint.text.trim());
    if (_fallbackKey.text.trim().isEmpty) {
      await _secureStorage.delete(key: 'fallback_key');
      await prefs.remove('fallback_key');
    } else {
      await _secureStorage.write(key: 'fallback_key', value: _fallbackKey.text.trim());
      await prefs.remove('fallback_key');
    }
    await prefs.setString('fallback_model', _fallbackModel.text.trim());
  }

  Future<void> _connectAndroid() async {
    final endpoint = _endpoint.text.trim();
    final model = _model.text.trim().isEmpty ? kFreePrimaryModel : _model.text.trim();
    final key = _apiKey.text.trim();
    final fallbackEndpoint = _fallbackEndpoint.text.trim();
    final fallbackKey = _fallbackKey.text.trim();
    final fallbackModel = _fallbackModel.text.trim();
    if (endpoint.isEmpty || key.isEmpty) {
      if (mounted) setState(() => _status = 'Введите AI URL и API key в Настройках');
      _setVisual(JarvisVisualState.error);
      return;
    }
    JarvisIpc? candidate;
    try {
      if (mounted) setState(() => _status = 'Проверяю подключение к AI API…');
      _setVisual(JarvisVisualState.thinking);

      // Persist entered credentials securely even if the first connection
      // check fails, so users do not lose the key while correcting settings.
      await _saveSettings();

      // Keep the active connection alive until the replacement has passed
      // a real chat probe. Failed settings/network attempts must not break a
      // previously working session or leak the candidate HttpClient.
      final next = await JarvisIpc.connectAi(
        endpoint,
        apiKey: key,
        model: model,
        fallbackUrl: fallbackEndpoint,
        fallbackKey: fallbackKey,
        fallbackModel: fallbackModel,
      );
      candidate = next;
      await next.checkConnection();
      _model.text = next.resolvedModel ?? _model.text.trim();
      await _saveSettings();

      final previous = _jarvis;
      _jarvis = next;
      candidate = null;
      await previous?.dispose();

      await _finishConnect();
      // Start hands-free voice only after the AI connection and first frame are ready.
      // Native speech service failures remain non-fatal inside _initVoice().
      await _initVoice();
      if (_voiceReady && mounted) {
        _voiceRunning = true;
        await _startVoiceLoop();
      }
    } catch (e) {
      await candidate?.dispose();
      if (mounted) setState(() => _status = 'Ошибка ИИ: $e');
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
    setState(() => _status = _android ? 'ИИ подключён · JARVIS активен' : 'JARVIS подключён · инструментов: ${tools.length}');
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

  Future<void> _toolSettings() async {
    Map<String, dynamic> current;
    try {
      final loaded = await _nativeTools.invokeMethod<Map<dynamic, dynamic>>('load_settings');
      current = Map<String, dynamic>.from(loaded ?? const {});
    } catch (e) {
      if (mounted) setState(() => _status = 'Не удалось загрузить настройки инструментов: $e');
      return;
    }
    if (!mounted) return;
    final cg = TextEditingController(text: current['coinglassApiKey']?.toString() ?? '');
    final okxEndpoint = TextEditingController(text: current['okxEndpoint']?.toString() ?? 'https://www.okx.com');
    final okxKey = TextEditingController(text: current['okxApiKey']?.toString() ?? '');
    final okxSecret = TextEditingController(text: current['okxSecretKey']?.toString() ?? '');
    final okxPass = TextEditingController(text: current['okxPassphrase']?.toString() ?? '');
    final dsaEndpoint = TextEditingController(text: current['dsaEndpoint']?.toString() ?? '');
    final dsaKey = TextEditingController(text: current['dsaApiKey']?.toString() ?? '');
    final save = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Настройки инструментов'),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Align(alignment: Alignment.centerLeft, child: Text('CoinGlass', style: TextStyle(fontWeight: FontWeight.bold))),
                TextField(controller: cg, obscureText: true, decoration: const InputDecoration(labelText: 'CoinGlass API Key')),
                const SizedBox(height: 12),
                const Align(alignment: Alignment.centerLeft, child: Text('OKX', style: TextStyle(fontWeight: FontWeight.bold))),
                TextField(controller: okxEndpoint, keyboardType: TextInputType.url, decoration: const InputDecoration(labelText: 'OKX Base URL')),
                TextField(controller: okxKey, obscureText: true, decoration: const InputDecoration(labelText: 'OKX API Key')),
                TextField(controller: okxSecret, obscureText: true, decoration: const InputDecoration(labelText: 'OKX Secret Key')),
                TextField(controller: okxPass, obscureText: true, decoration: const InputDecoration(labelText: 'OKX Passphrase')),
                const SizedBox(height: 12),
                const Align(alignment: Alignment.centerLeft, child: Text('Daily Stock Analysis', style: TextStyle(fontWeight: FontWeight.bold))),
                TextField(controller: dsaEndpoint, keyboardType: TextInputType.url, decoration: const InputDecoration(labelText: 'Service Base URL')),
                TextField(controller: dsaKey, obscureText: true, decoration: const InputDecoration(labelText: 'Service API Key')),
                const SizedBox(height: 8),
                const Text('OKX по умолчанию использует демо-режим. Не отключайте защиту от реальных сделок без необходимости.', style: TextStyle(fontSize: 12)),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Отмена')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Сохранить')),
        ],
      ),
    );
    if (save == true && mounted) {
      try {
        current.addAll({
          'coinglassApiKey': cg.text.trim(),
          'okxEndpoint': okxEndpoint.text.trim().isEmpty ? 'https://www.okx.com' : okxEndpoint.text.trim(),
          'okxApiKey': okxKey.text.trim(),
          'okxSecretKey': okxSecret.text.trim(),
          'okxPassphrase': okxPass.text.trim(),
          'dsaEndpoint': dsaEndpoint.text.trim(),
          'dsaApiKey': dsaKey.text.trim(),
        });
        await _nativeTools.invokeMethod<bool>('save_settings', current);
        if (mounted) setState(() => _status = 'Настройки инструментов сохранены');
      } catch (e) {
        if (mounted) setState(() => _status = 'Ошибка сохранения настроек инструментов: $e');
      }
    }
    cg.dispose();
    okxEndpoint.dispose();
    okxKey.dispose();
    okxSecret.dispose();
    okxPass.dispose();
    dsaEndpoint.dispose();
    dsaKey.dispose();
  }

  IconData _toolGroupIcon(String group) => switch (group) {
    'Интернет' => Icons.public_rounded,
    'Файлы' => Icons.folder_open_rounded,
    'База данных' => Icons.storage_rounded,
    'Система и память' => Icons.memory_rounded,
    'Криптоинструменты' => Icons.currency_bitcoin_rounded,
    'Аналитика' => Icons.query_stats_rounded,
    _ => Icons.build_circle_outlined,
  };

  Future<void> _showTools() async {
    if (!_android) return;
    const groups = <String, List<Map<String, String>>>{
      'Интернет': [
        {'name': 'open_url', 'title': 'Открыть ссылку', 'args': '{"url":"https://example.com"}', 'hint': 'Открывает сайт в браузере'},
        {'name': 'google_search', 'title': 'Поиск в интернете', 'args': '{"query":"новости технологий","limit":8}', 'hint': 'Поиск по веб-страницам'},
        {'name': 'web_get', 'title': 'Получить содержимое сайта', 'args': '{"url":"https://example.com"}', 'hint': 'Загрузить текст/ответ URL'},
        {'name': 'weather', 'title': 'Погода в городе', 'args': '{"city":"Одесса"}', 'hint': 'Текущая погода через Open-Meteo'},
        {'name': 'http_request', 'title': 'HTTP-запрос', 'args': '{"method":"GET","url":"https://example.com","body":"","headers":"{}"}', 'hint': 'Настраиваемый HTTP/HTTPS запрос'},
        {'name': 'download_file', 'title': 'Скачать файл', 'args': '{"url":"https://example.com/file.txt","filename":"file.txt"}', 'hint': 'Сохранение в папку приложения'},
      ],
      'Файлы': [
        {'name': 'file_roots', 'title': 'Папки JARVIS', 'args': '{}', 'hint': 'Показать доступные папки приложения'},
        {'name': 'file_list', 'title': 'Список файлов', 'args': '{"path":""}', 'hint': 'Просмотр разрешённых папок приложения'},
        {'name': 'file_read', 'title': 'Прочитать файл', 'args': '{"path":"example.txt"}', 'hint': 'Чтение текстового файла'},
        {'name': 'file_write', 'title': 'Создать/перезаписать файл', 'args': '{"path":"notes.txt","content":"Текст"}', 'hint': 'Запись в папку приложения'},
        {'name': 'file_append', 'title': 'Дополнить файл', 'args': '{"path":"notes.txt","content":"\\nНовая строка"}', 'hint': 'Добавление текста в файл'},
        {'name': 'file_mkdir', 'title': 'Создать папку', 'args': '{"path":"documents"}', 'hint': 'Создание папки в хранилище приложения'},
        {'name': 'file_copy', 'title': 'Копировать файл', 'args': '{"from":"notes.txt","to":"notes-copy.txt"}', 'hint': 'Копирование внутри разрешённого хранилища'},
        {'name': 'file_move', 'title': 'Переместить файл', 'args': '{"from":"notes-copy.txt","to":"archive/notes.txt"}', 'hint': 'Перемещение внутри разрешённого хранилища'},
        {'name': 'file_delete', 'title': 'Удалить файл', 'args': '{"path":"notes-copy.txt","confirm":true}', 'hint': 'Разрушительное действие — требуется confirm=true'},
      ],
      'База данных': [
        {'name': 'db_tables', 'title': 'Таблицы базы', 'args': '{"database":"jarvis.db"}', 'hint': 'Список таблиц локальной SQLite базы'},
        {'name': 'db_query', 'title': 'SQL-запрос чтения', 'args': '{"database":"jarvis.db","sql":"SELECT name FROM sqlite_master","limit":100}', 'hint': 'Чтение данных SQLite'},
        {'name': 'db_exec', 'title': 'Выполнить SQL', 'args': '{"database":"jarvis.db","sql":"CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, text TEXT)","confirm":true}', 'hint': 'Изменение БД — требуется confirm=true'},
      ],
      'Система и память': [
        {'name': 'device_info', 'title': 'Информация об устройстве', 'args': '{}', 'hint': 'Модель Android и состояние хранилища'},
        {'name': 'time_now', 'title': 'Текущее время', 'args': '{}', 'hint': 'Локальное время устройства'},
        {'name': 'clipboard_get', 'title': 'Прочитать буфер обмена', 'args': '{}', 'hint': 'Получить текущий текст буфера обмена'},
        {'name': 'clipboard_set', 'title': 'Записать в буфер обмена', 'args': '{"text":"Текст для копирования"}', 'hint': 'Копирование текста'},
        {'name': 'self_snapshot', 'title': 'Память JARVIS', 'args': '{}', 'hint': 'Показать сохранённые правила и записи'},
        {'name': 'self_behavior', 'title': 'Правила поведения', 'args': '{}', 'hint': 'Показать активные правила помощника'},
        {'name': 'self_learn', 'title': 'Запомнить правило', 'args': '{"category":"rules","text":"Всегда отвечай на русском","priority":80}', 'hint': 'Добавить правило в локальную память'},
        {'name': 'self_improve', 'title': 'Улучшить поведение', 'args': '{"instruction":"Не сообщай об успешном выполнении без проверки"}', 'hint': 'Сохранить инструкцию для самоулучшения'},
        {'name': 'self_forget', 'title': 'Удалить запись из памяти', 'args': '{"text":"фрагмент записи"}', 'hint': 'Удаляет совпадающие записи из локальной памяти'},
        {'name': 'self_clear', 'title': 'Очистить память', 'args': '{"confirm":true}', 'hint': 'Опасно: удаляет всю локальную память'},
      ],
      'Криптоинструменты': [
        {'name': 'okx_public', 'title': 'Рыночные данные OKX', 'args': '{"path":"/api/v5/market/ticker?instId=BTC-USDT"}', 'hint': 'Публичные данные рынка'},
        {'name': 'okx_account', 'title': 'Баланс OKX', 'args': '{"path":"/api/v5/account/balance"}', 'hint': 'Требуются API Key, Secret и Passphrase'},
        {'name': 'okx_order', 'title': 'Выставить ордер OKX', 'args': '{"body":"{}","confirm":false}', 'hint': 'Реальная сделка требует отдельного подтверждения'},
        {'name': 'coinglass', 'title': 'Данные CoinGlass', 'args': '{"path":"/api/futures/supported-coins"}', 'hint': 'Требуется CoinGlass API Key в настройках Android'},
      ],
      'Аналитика': [
        {'name': 'daily_stock_analysis', 'title': 'Проверить Daily Stock Analysis', 'args': '{"path":"/health","method":"GET","body":"{}"}', 'hint': 'Требуется URL сервиса'},
        {'name': 'dsa_analyze', 'title': 'Анализ акции', 'args': '{"stock_code":"AAPL","stock_name":"Apple","report_type":"detailed"}', 'hint': 'Требуется настроенный URL Daily Stock Analysis'},
        {'name': 'dsa_market_review', 'title': 'Обзор рынка', 'args': '{"region":"us"}', 'hint': 'Требуется настроенный URL Daily Stock Analysis'},
      ],
    };
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: kPanel,
      builder: (ctx) => SafeArea(
        child: DraggableScrollableSheet(
          expand: false,
          initialChildSize: 0.8,
          minChildSize: 0.45,
          maxChildSize: 0.95,
          builder: (context, scrollController) => ListView(
            controller: scrollController,
            padding: const EdgeInsets.all(16),
            children: [
              const Text('ИНСТРУМЕНТЫ JARVIS', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800, letterSpacing: 1.2)),
              const SizedBox(height: 8),
              const Text('Доступны инструменты, реализованные в Android-версии. Для сервисов с ключами сначала заполните их настройки.', style: TextStyle(fontSize: 12, color: Colors.white70)),
              const SizedBox(height: 8),
              FilledButton.tonalIcon(
                onPressed: () { Navigator.pop(ctx); _toolSettings(); },
                icon: const Icon(Icons.settings_outlined),
                label: const Text('Настройки ключей и сервисов'),
              ),
              for (final group in groups.entries)
                Card(
                  color: const Color(0xFF101D2A),
                  margin: const EdgeInsets.only(top: 8),
                  clipBehavior: Clip.antiAlias,
                  child: ExpansionTile(
                    initiallyExpanded: group.key == 'Интернет' || group.key == 'Система и память',
                    leading: Icon(_toolGroupIcon(group.key), color: _visualColor),
                    title: Text(group.key, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                    subtitle: Text('${group.value.length} инструментов', style: const TextStyle(fontSize: 12, color: Colors.white60)),
                    children: [
                      for (final tool in group.value)
                        ListTile(
                          contentPadding: const EdgeInsets.fromLTRB(16, 0, 12, 0),
                          leading: const Icon(Icons.play_circle_outline_rounded, size: 22),
                          title: Text(tool['title']!, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                          subtitle: Text(tool['hint']!, style: const TextStyle(fontSize: 12, height: 1.3)),
                          trailing: const Icon(Icons.chevron_right_rounded, size: 20),
                          onTap: () {
                            Navigator.pop(ctx);
                            _runAndroidTool(tool['name']!, tool['title']!, tool['args']!);
                          },
                        ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _runAndroidTool(String name, String title, String initialArgs) async {
    final argsController = TextEditingController(text: initialArgs);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: SizedBox(
          width: 520,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Параметры запуска. Для обычного использования оставьте значения по умолчанию. Изменяйте JSON только если понимаете параметры.', style: TextStyle(fontSize: 12, height: 1.35)),
              const SizedBox(height: 8),
              TextField(
                controller: argsController,
                minLines: 3,
                maxLines: 7,
                style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
                decoration: const InputDecoration(
                  labelText: 'Параметры',
                  helperText: 'Формат JSON',
                  alignLabelWithHint: true,
                  border: OutlineInputBorder(),
                  hintText: '{"key":"value"}',
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Отмена')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Запустить')),
        ],
      ),
    );
    if (confirmed != true || !mounted) { argsController.dispose(); return; }
    setState(() { _busy = true; _status = 'Выполняю: $title'; });
    try {
      final decoded = jsonDecode(argsController.text);
      if (decoded is! Map<String, dynamic>) throw const FormatException('Нужен JSON-объект');
      final result = await _nativeTools.invokeMethod<dynamic>('android_tool', {
        'name': name,
        'args': jsonEncode(decoded),
      });
      final output = result is String ? result : const JsonEncoder.withIndent('  ').convert(result);
      if (mounted) {
        setState(() {
          _messages.add(_Msg('$title\n$output', isUser: false));
          _status = 'Инструмент выполнен: $title';
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _messages.add(_Msg('$title: ошибка — $e', isUser: false));
          _status = 'Ошибка инструмента: $e';
          _visualState = JarvisVisualState.error;
        });
      }
    } finally {
      argsController.dispose();
      if (mounted) setState(() => _busy = false);
    }
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
          const Align(alignment: Alignment.centerLeft, child: Text('Основной AI-провайдер', style: TextStyle(fontWeight: FontWeight.bold))),
          TextField(controller: _endpoint, keyboardType: TextInputType.url, decoration: const InputDecoration(labelText: 'Base URL', hintText: 'https://generativelanguage.googleapis.com/v1beta/openai')),
          TextField(controller: _apiKey, obscureText: true, decoration: const InputDecoration(labelText: 'API Key')),
          TextField(controller: _model, decoration: const InputDecoration(labelText: 'Модель (необязательно)', hintText: 'Оставьте пустым для автоопределения')),
          const SizedBox(height: 10),
          const Align(alignment: Alignment.centerLeft, child: Text('Резервный AI (необязательно)', style: TextStyle(fontWeight: FontWeight.bold))),
          TextField(controller: _fallbackEndpoint, keyboardType: TextInputType.url, decoration: const InputDecoration(labelText: 'Резервный Base URL')),
          TextField(controller: _fallbackKey, obscureText: true, decoration: const InputDecoration(labelText: 'Резервный API Key')),
          TextField(controller: _fallbackModel, decoration: const InputDecoration(labelText: 'Резервная модель')),
          const SizedBox(height: 8),
          const Text(
            'Для Gemini: ключ из Google AI Studio. Если модель не указана, JARVIS найдёт доступные модели через API. Доступность зависит от ключа и квоты.',
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
        setState(() => _status = 'Ошибка ИИ: $e');
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
    final screenSize = MediaQuery.sizeOf(context);
    final screenHeight = screenSize.height;
    final compactLayout = screenSize.width < 760;
    final sceneHeight = compactLayout
        ? (screenHeight * 0.40).clamp(250.0, 330.0).toDouble()
        : (screenHeight * 0.48).clamp(300.0, 390.0).toDouble();
    final connected = _jarvis != null;
    return Scaffold(
      appBar: AppBar(
        title: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.bubble_chart, color: Color(0xFF42E8FF), size: 25),
            SizedBox(width: 9),
            Text('JARVIS', style: TextStyle(letterSpacing: 3, fontWeight: FontWeight.w700)),
            SizedBox(width: 7),
            Text('XXX', style: TextStyle(color: Color(0xFF42E8FF), fontSize: 11, letterSpacing: 2)),
          ],
        ),
        actions: [
          IconButton(tooltip: 'Инструменты', onPressed: _showTools, icon: const Icon(Icons.folder_open_rounded)),
          IconButton(tooltip: 'Настройки AI', onPressed: _settings, icon: const Icon(Icons.tune_rounded)),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            SizedBox(
              height: sceneHeight,
              width: double.infinity,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  Positioned.fill(
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: RadialGradient(
                          center: Alignment.center,
                          radius: 0.9,
                          colors: [
                            _visualColor.withValues(alpha: 0.10),
                            const Color(0xFF07111D).withValues(alpha: 0.55),
                            Colors.transparent,
                          ],
                          stops: const [0, 0.58, 1],
                        ),
                      ),
                    ),
                  ),
                  Positioned.fill(
                    child: JarvisReactor(
                      color: _visualColor,
                      state: _visualState,
                      activity: _voiceLevel,
                    ),
                  ),
                  Positioned(
                    bottom: 12,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          'СИСТЕМА',
                          style: TextStyle(
                            color: _visualColor,
                            fontSize: 12,
                            letterSpacing: 3,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          _visualLabel,
                          style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.72),
                            fontSize: 10,
                            letterSpacing: 1.8,
                          ),
                        ),
                        const SizedBox(height: 4),
                        SizedBox(
                          width: MediaQuery.sizeOf(context).width * 0.82,
                          child: Text(
                            _status,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.58),
                              fontSize: 10,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 0, 14, 8),
              child: Row(
                children: [
                  Expanded(
                    child: _deckAction(
                      icon: Icons.hub_outlined,
                      label: 'СИСТЕМА',
                      active: true,
                      onTap: () {
                        setState(() {
                          _status = connected
                              ? 'Система подключена и готова'
                              : 'Ожидается подключение AI в настройках';
                        });
                      },
                    ),
                  ),
                  const SizedBox(width: 7),
                  Expanded(
                    child: _deckAction(
                      icon: Icons.tune_rounded,
                      label: 'НАСТРОЙКИ',
                      active: false,
                      onTap: _settings,
                    ),
                  ),
                ],
              ),
            ),
            const Divider(height: 1, color: Color(0xFF182736)),
            Expanded(
              child: _messages.isEmpty && _streamText.isEmpty
                  ? Center(
                      child: Padding(
                        padding: const EdgeInsets.all(24),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.bolt_rounded, color: _visualColor, size: 28),
                            const SizedBox(height: 10),
                            const Text('Командный интерфейс готов',
                              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                            const SizedBox(height: 6),
                            Text('Введите запрос или включите голосовое управление.',
                              textAlign: TextAlign.center,
                              style: TextStyle(color: Colors.white.withValues(alpha: 0.55), fontSize: 12)),
                          ],
                        ),
                      ),
                    )
                  : ListView.builder(
                      controller: _scroll,
                      padding: const EdgeInsets.fromLTRB(14, 12, 14, 8),
                      itemCount: _messages.length + (_streamText.isNotEmpty ? 1 : 0),
                      itemBuilder: (context, index) {
                        if (_streamText.isNotEmpty && index == _messages.length) {
                          return Align(alignment: Alignment.centerLeft, child: _messageBubble(_streamText, false));
                        }
                        final message = _messages[index];
                        return Align(
                          alignment: message.isUser ? Alignment.centerRight : Alignment.centerLeft,
                          child: _messageBubble(message.text, message.isUser),
                        );
                      },
                    ),
            ),
            if (_android && _heardText.isNotEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 0, 14, 5),
                child: Row(
                  children: [
                    Icon(Icons.graphic_eq, color: _visualColor, size: 15),
                    const SizedBox(width: 6),
                    Expanded(child: Text(_heardText, maxLines: 1, overflow: TextOverflow.ellipsis,
                      style: TextStyle(color: Colors.white.withValues(alpha: 0.62), fontSize: 11))),
                  ],
                ),
              ),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 8, 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Expanded(
                    child: TextField(
                      controller: _input,
                      minLines: 1,
                      maxLines: 4,
                      textInputAction: TextInputAction.newline,
                      onSubmitted: _send,
                      decoration: InputDecoration(
                        hintText: 'Передать команду JARVIS…',
                        filled: true,
                        fillColor: kPanel,
                        prefixIcon: const Icon(Icons.terminal_rounded, color: Color(0xFF42E8FF)),
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide.none),
                        contentPadding: const EdgeInsets.symmetric(horizontal: 15, vertical: 12),
                      ),
                    ),
                  ),
                  const SizedBox(width: 6),
                  IconButton.filled(tooltip: 'Отправить команду',
                    onPressed: _busy ? null : () => _send(_input.text),
                    icon: const Icon(Icons.arrow_upward_rounded)),
                  if (_android)
                    IconButton(
                      tooltip: _voiceRunning ? 'Выключить голосовое управление' : 'Включить голосовое управление',
                      onPressed: _busy ? null : () async {
                        try {
                          if (_voiceRunning) {
                            _speechSession++;
                            _voiceRunning = false;
                            _voiceLevel = 0;
                            _voiceRestartTimer?.cancel();
                            await _speech.stop();
                            if (mounted) {
                              setState(() {
                                _status = 'Голосовое управление выключено';
                                _visualState = JarvisVisualState.idle;
                              });
                            }
                          } else {
                            if (!_voiceReady) await _initVoice();
                            if (_voiceReady && mounted) {
                              _voiceRunning = true;
                              await _startVoiceLoop();
                            }
                          }
                        } catch (e, stack) {
                          debugPrint('JARVIS microphone button failed: $e\\n$stack');
                          _voiceRunning = false;
                          if (mounted) {
                            setState(() {
                              _status = 'Микрофон недоступен: $e';
                              _visualState = JarvisVisualState.error;
                            });
                          }
                        }
                      },
                      icon: Icon(_voiceRunning ? Icons.mic_rounded : Icons.mic_none_rounded,
                        color: _voiceRunning ? _visualColor : null),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _deckAction({
    required IconData icon,
    required String label,
    required bool active,
    required VoidCallback onTap,
  }) {
    final color = active ? kCyan : const Color(0xFF8294A8);
    return Material(
      color: const Color(0xFF0A111B),
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        borderRadius: BorderRadius.circular(10),
        onTap: onTap,
        child: Container(
          constraints: const BoxConstraints(minHeight: 42),
          padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 7),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: color.withValues(alpha: active ? 0.38 : 0.16)),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 14, color: color),
              const SizedBox(width: 5),
              Flexible(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: color,
                    fontSize: 8,
                    letterSpacing: 0.55,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
        ),
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
