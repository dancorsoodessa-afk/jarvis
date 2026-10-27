import 'dart:async';
import 'dart:io';
import 'package:flutter/services.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:flutter_tts/flutter_tts.dart';
import 'jarvis_client.dart';
import 'crypto/crypto_tools.dart';
import 'crypto/crypto_screen.dart';
import 'osint/osint_screen.dart';
import 'jarvis_reactor.dart';
import 'tools/calculator/calculator_screen.dart';
import 'tools/clipboard/clipboard_screen.dart';
import 'tools/internet/internet_screen.dart';
import 'tools/memory/memory_screen.dart';
import 'tools/system/system_screen.dart';
import 'tools/files/files_screen.dart';

const kCyan = Color(0xFF37D5EE);
const kBg = Color(0xFF05080F);
const kPanel = Color(0xFF0D1622);
const kFreeModel = 'gemini-3.8-flash';
const kGeminiEndpoint = 'https://generativelanguage.googleapis.com/v1beta/openai/';
const kDefaultEndpoint = kGeminiEndpoint;

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

// Android client state and provider configuration.
class _JarvisHomePageState extends State<JarvisHomePage> {
  JarvisIpc? _jarvis;
  final _input = TextEditingController();
  final _endpoint = TextEditingController();
  final _apiKey = TextEditingController();
  final _model = TextEditingController();
  final _fallbackEndpoint = TextEditingController();
  final _fallbackKey = TextEditingController();
  final _fallbackModel = TextEditingController();
  final _coinglassKey = TextEditingController();
  final _scroll = ScrollController();
  final _messages = <_Msg>[];
  final stt.SpeechToText _speech = stt.SpeechToText();
  final FlutterTts _tts = FlutterTts();
  StreamSubscription<String>? _partialSub;
  Timer? _visualTimer;
  Timer? _voiceRestartTimer;
  Timer? _commandTimer;
  bool _busy = false;
  bool _showCryptoDashboard = false;
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

  Future<void> _toggleVoice() async {
    if (!_android || _voiceStarting) return;
    if (_voiceRunning) {
      _voiceRunning = false;
      _wakeArmed = false;
      _voiceRestartTimer?.cancel();
      if (_voiceReady) {
        try { await _speech.stop(); } catch (e) {
          debugPrint('JARVIS speech stop failed: $e');
        }
      }
      if (mounted) {
        setState(() => _status = 'Голос остановлен');
        _setVisual(JarvisVisualState.idle);
      }
      return;
    }
    try {
      await _initVoice();
      if (!mounted || !_voiceReady) return;
      _voiceRunning = true;
      _wakeArmed = false;
      await _startVoiceLoop();
    } catch (e, stack) {
      debugPrint('JARVIS voice start failed: $e');
      debugPrintStack(stackTrace: stack);
      _voiceRunning = false;
      if (mounted) {
        setState(() => _status = 'Микрофон недоступен: $e');
        _setVisual(JarvisVisualState.error);
      }
    }
  }

  Future<void> _startVoiceLoop() async {
    if (!_android || !_voiceReady || _voiceStarting || _ttsSpeaking || _busy) return;
    _voiceStarting = true;
    try {
      await _speech.stop();
      await Future<void>.delayed(const Duration(milliseconds: 250));
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
    final match = RegExp(r'\b(?:джарвис|jarvis)\b').firstMatch(normalized);
    if (match == null) return null;
    final command = normalized.substring(match.end).trim();
    return command.isEmpty ? '' : command;
  }

  Future<void> _onSpeechResult(dynamic result) async {
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
      final savedEndpoint = prefs.getString('endpoint')?.trim() ?? '';
      final savedModel = prefs.getString('model')?.trim() ?? '';
      final useGeminiDefaults = savedEndpoint.isEmpty ||
          (savedEndpoint == kDefaultEndpoint &&
              (savedModel.isEmpty || savedModel == 'gpt-4o-mini' || savedModel == 'llama-3.3-70b-versatile' || savedModel == 'gemini-2.5-flash'));
      _endpoint.text = useGeminiDefaults ? kGeminiEndpoint : savedEndpoint;
      _model.text = useGeminiDefaults ? kFreeModel : (savedModel.isEmpty ? kFreeModel : savedModel);
      _apiKey.text = _cleanApiKey(prefs.getString('api_key') ?? '');
      _fallbackEndpoint.text = prefs.getString('fallback_endpoint')?.trim() ?? '';
      _fallbackKey.text = _cleanApiKey(prefs.getString('fallback_key') ?? '');
      _fallbackModel.text = prefs.getString('fallback_model')?.trim() ?? '';
      // Do not initialize native speech/TTS services during app startup.
      // Some Android speech services can crash the native process before Dart
      // error handling runs. Initialize voice only after the user taps the mic.
      if (!mounted) return;
      if (_apiKey.text.isEmpty) {
        setState(() => _status = 'Введите API key Gemini в настройках');
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

  String _cleanApiKey(String value) {
    var key = value.trim();
    if (key.toLowerCase().startsWith('bearer ')) key = key.substring(7).trim();
    return key;
  }

  Future<void> _saveSettings() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('endpoint', _endpoint.text.trim());
    await prefs.setString('model', _model.text.trim());
    await prefs.setString('api_key', _cleanApiKey(_apiKey.text));
    await prefs.setString('fallback_endpoint', _fallbackEndpoint.text.trim());
    await prefs.setString('fallback_key', _cleanApiKey(_fallbackKey.text));
    await prefs.setString('fallback_model', _fallbackModel.text.trim());
  }

  Future<void> _connectAndroid() async {
    final endpoint = _endpoint.text.trim();
    final model = _model.text.trim();
    final key = _apiKey.text.trim();
    if (endpoint.isEmpty || key.isEmpty) {
      if (mounted) setState(() => _status = 'Введите API key Gemini в настройках');
      _setVisual(JarvisVisualState.error);
      return;
    }
    try {
      await _saveSettings();
      if (mounted) setState(() => _status = 'Проверяю AI и API key…');
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
    if (_android && _voiceReady) {
      _voiceRunning = true;
      _startVoiceLoop();
    }
  }

  Future<void> _settings() async {
    if (!_android) return;
    // Opening AI settings must never call an uninitialized native speech plugin.
    _voiceRestartTimer?.cancel();
    if (_voiceReady && _voiceRunning) {
      _voiceRunning = false;
      _wakeArmed = false;
      try { await _speech.stop(); } catch (e) {
        debugPrint('JARVIS speech stop before settings failed: $e');
      }
    }
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('JARVIS — настройки'),
        content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Align(alignment: Alignment.centerLeft, child: Text('Основной AI', style: TextStyle(fontWeight: FontWeight.bold))),
          TextField(controller: _endpoint, enabled: true, readOnly: false, enableInteractiveSelection: true, autocorrect: false, maxLines: 1, keyboardType: TextInputType.url, decoration: InputDecoration(labelText: 'AI URL', hintText: 'https://generativelanguage.googleapis.com/v1beta/openai', suffixIcon: IconButton(tooltip: 'Очистить адрес', onPressed: () => _endpoint.clear(), icon: const Icon(Icons.clear)))),
          TextField(controller: _apiKey, obscureText: true, decoration: const InputDecoration(labelText: 'API Key')),
          TextField(controller: _model, decoration: const InputDecoration(labelText: 'Model', hintText: 'gemini-2.5-flash')),
          const SizedBox(height: 12),
          const Align(alignment: Alignment.centerLeft, child: Text('Резервный AI · при 429/5xx/сбое', style: TextStyle(fontWeight: FontWeight.bold))),
          TextField(controller: _fallbackEndpoint, keyboardType: TextInputType.url, decoration: const InputDecoration(labelText: 'Резервный AI URL')),
          TextField(controller: _fallbackKey, obscureText: true, decoration: const InputDecoration(labelText: 'Резервный API Key')),
          TextField(controller: _fallbackModel, decoration: const InputDecoration(labelText: 'Резервная Model')),
          TextField(controller: _coinglassKey, obscureText: true, autocorrect: false, enableSuggestions: false, decoration: const InputDecoration(labelText: 'CoinGlass API Key (не сохраняется)')),
          const SizedBox(height: 8),
          const Text('Голос: автоматическое ожидание «Джарвис».', style: TextStyle(fontSize: 12)),
        ])),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Отмена')),
          FilledButton(onPressed: () { Navigator.pop(ctx); _connectAndroid(); }, child: const Text('Сохранить и подключить')),
        ],
      ),
    );
  }

  Future<void> _showVoiceSettings() async {
    if (!_android) return;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Настройки микрофона'),
        content: Text(
          'Состояние: ${_voiceReady ? "готов" : "не инициализирован"}\n'
          'Прослушивание: ${_voiceRunning ? "включено" : "выключено"}\n'
          'Распознавание запускается только после нажатия кнопки микрофона.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Закрыть')),
          FilledButton(
            onPressed: () {
              Navigator.pop(ctx);
              _toggleVoice();
            },
            child: Text(_voiceRunning ? 'Остановить' : 'Проверить микрофон'),
          ),
        ],
      ),
    );
  }

  String _cryptoSymbol(String text) {
    final t = text.toLowerCase();
    if (RegExp(r'\b(eth|ethereum)\b|эфир|эфириум').hasMatch(t)) return 'ETH-USDT';
    if (RegExp(r'\b(sol|solana)\b|солан').hasMatch(t)) return 'SOL-USDT';
    if (RegExp(r'\b(xrp)\b|рипл').hasMatch(t)) return 'XRP-USDT';
    return 'BTC-USDT';
  }

  Future<bool> _handleCryptoTool(String text) async {
    if (!_android) return false;
    final t = text.toLowerCase();
    final isCrypto = RegExp(r'крипт|биткоин|bitcoin|\bbtc\b|эфир|эфириум|\beth\b|солан|\bsol\b|рипл|\bxrp\b|rsi|sma|фандинг|funding|открыт.{0,12}интерес|open interest|техническ.{0,12}анализ|индикатор|coinglass|ликвидац|лонг|шорт|cvd|long.?short').hasMatch(t);
    if (!isCrypto) return false;
    final symbol = _cryptoSymbol(text);
    setState(() {
      _messages.add(_Msg(text, isUser: true));
      _busy = true;
      _showCryptoDashboard = true;
      _visualState = JarvisVisualState.thinking;
      _status = 'Криптоинструмент · запрос к OKX…';
    });
    try {
      String result;
      if (RegExp(r'coinglass|ликвидац|лонг|шорт|cvd|long.?short').hasMatch(t)) {
        if (_coinglassKey.text.trim().isEmpty) {
          result = 'Для ликвидаций, Long/Short, CVD и агрегированного Open Interest нужен CoinGlass API key. Откройте настройки JARVIS и укажите ключ в поле CoinGlass API Key.';
        } else {
          final data = await JarvisCrypto.coinglassSnapshot(apiKey: _coinglassKey.text.trim(), symbol: symbol.replaceAll('-USDT', ''), interval: '1h');
          result = data.entries.map((entry) {
            final value = entry.value;
            final latest = value is List ? (value.isEmpty ? 'нет данных' : value.last.toString()) : value.toString();
            final short = latest.length > 520 ? '${latest.substring(0, 520)}…' : latest;
            return '${entry.key.toUpperCase()}: ${short}';
          }).join('\n\n');
        }
      } else if (RegExp(r'фандинг|funding|открыт.{0,12}интерес|open interest|\boi\b').hasMatch(t)) {
        final inst = '${symbol.replaceAll('-USDT', '')}-USDT-SWAP';
        final d = await JarvisCrypto.derivatives(symbol: inst);
        final funding = d['funding'];
        final oi = d['open_interest'];
        result = '${symbol.replaceAll('-USDT', '')} · деривативы\n'
          'Funding rate: ${funding is Map ? funding['fundingRate'] ?? funding['funding_rate'] ?? 'нет данных' : 'нет данных'}\n'
          'Open interest: ${oi is Map ? oi['oi'] ?? oi['openInterest'] ?? oi['open_interest'] ?? 'нет данных' : 'нет данных'}';
      } else if (RegExp(r'rsi|sma|индикатор|техническ.{0,12}анализ|свеч|график').hasMatch(t)) {
        final candles = await JarvisCrypto.candles(symbol: symbol, timeframe: '1H', limit: 100);
        final m = JarvisCrypto.indicators(candles);
        String val(String key, {int digits = 2}) => m[key] == null ? 'недостаточно данных' : (m[key] as double).toStringAsFixed(digits);
        result = '${symbol.replaceAll('-USDT', '')} · технические показатели (1H)\n'
          'Цена закрытия: ${val('last')} USDT\n'
          'Изменение: ${val('change_pct')}%\n'
          'SMA20: ${val('sma20')}\nSMA50: ${val('sma50')}\nRSI14: ${val('rsi14')}';
      } else {
        final allMarkets = RegExp(r'все|рынк|обзор').hasMatch(t) || (RegExp(r'\bbtc\b').hasMatch(t) && RegExp(r'\beth\b').hasMatch(t) && RegExp(r'\bsol\b').hasMatch(t));
        final symbols = allMarkets ? ['BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'XRP-USDT'] :
          RegExp(r'\bbtc\b|биткоин|bitcoin').hasMatch(t) ? ['BTC-USDT'] :
          RegExp(r'\beth\b|эфир|эфириум').hasMatch(t) ? ['ETH-USDT'] :
          RegExp(r'\bsol\b|солан').hasMatch(t) ? ['SOL-USDT'] :
          RegExp(r'\bxrp\b|рипл').hasMatch(t) ? ['XRP-USDT'] :
          ['BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'XRP-USDT'];
        final rows = await JarvisCrypto.tickers(symbols: symbols);
        result = rows.map((row) {
          final id = row['instId']?.toString() ?? 'актив';
          final last = double.tryParse(row['last']?.toString() ?? '') ?? 0;
          final open = double.tryParse(row['open24h']?.toString() ?? '') ?? 0;
          final change = open == 0 ? 0 : ((last - open) / open) * 100;
          return '$id: $last USDT  |  24ч: ${change >= 0 ? '+' : ''}${change.toStringAsFixed(2)}%';
        }).join('\n');
        if (result.isEmpty) result = 'OKX не вернул данные по запрошенным активам.';
      }
      if (mounted) {
        setState(() {
          _messages.add(_Msg(result, isUser: false));
          _status = 'Криптоинструмент выполнен · источник OKX';
          _visualState = JarvisVisualState.confirmation;
        });
      }
      _returnToIdle(const Duration(milliseconds: 1200));
    } catch (e) {
      if (mounted) {
        setState(() {
          _messages.add(_Msg('Криптоинструмент: ошибка запроса OKX — $e', isUser: false));
          _status = 'Криптоинструмент недоступен';
          _visualState = JarvisVisualState.error;
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
    return true;
  }

  Future<void> _send(String text, {bool speakReply = false}) async {
    text = text.trim();
    if (text.isEmpty || _busy) return;
    if (await _handleTimer(text)) { _input.clear(); return; }
    if (await _handleCryptoTool(text)) { _input.clear(); return; }
    if (_jarvis == null) {
      if (mounted) setState(() => _status = 'AI не подключён · откройте настройки');
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
      if (speakReply) await _speak('Произошла ошибка. Проверьте AI URL, API key и Model.');
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
    final duration = await _parseTimer(text);
    if (duration == null) return false;
    _commandTimer?.cancel();
    final mins = duration.inMinutes;
    final reply = mins > 0 ? 'Таймер установлен на $mins минут.' : 'Таймер установлен на ${duration.inSeconds} секунд.';
    if (mounted) {
      setState(() { _messages.add(_Msg(reply, isUser: false)); _status = reply; });
    }
    await _speak(reply);
    _commandTimer = Timer(duration, () async {
      if (!mounted) return;
      setState(() => _status = 'Таймер завершён');
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('JARVIS — таймер'),
          content: const Text('Время вышло.'),
          actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Закрыть'))],
        ),
      );
    });
    return true;
  }

  Future<void> _stopNativeVoiceSafely() async {
    if (!_voiceReady) return;
    try { await _speech.stop(); } catch (e) {
      debugPrint('JARVIS speech dispose failed: $e');
    }
    try { await _tts.stop(); } catch (e) {
      debugPrint('JARVIS TTS dispose failed: $e');
    }
  }

  @override
  void dispose() {
    _partialSub?.cancel();
    _visualTimer?.cancel();
    _voiceRestartTimer?.cancel();
    _commandTimer?.cancel();
    unawaited(_stopNativeVoiceSafely());
    _jarvis?.dispose();
    _input.dispose();
    _endpoint.dispose();
    _apiKey.dispose();
    _model.dispose();
    _fallbackEndpoint.dispose();
    _fallbackKey.dispose();
    _fallbackModel.dispose();
    _coinglassKey.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Widget _hudPill(String label, String value, Color color) => Container(
    margin: const EdgeInsets.only(right: 7),
    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
    decoration: BoxDecoration(color: kPanel, border: Border.all(color: color.withValues(alpha: .25)), borderRadius: BorderRadius.circular(5)),
    child: Row(mainAxisSize: MainAxisSize.min, children: [
      Container(width: 5, height: 5, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
      const SizedBox(width: 5),
      Text('$label  ', style: const TextStyle(color: Colors.white38, fontSize: 8, letterSpacing: 1)),
      Text(value, style: TextStyle(color: color, fontSize: 8, fontWeight: FontWeight.bold, letterSpacing: .5)),
    ]),
  );

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('JARVIS'), actions: [if (_android) IconButton(onPressed: _settings, tooltip: 'Настройки AI', icon: const Icon(Icons.settings))]),
      drawer: _android ? Drawer(
        backgroundColor: kBg,
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.all(12),
            children: [
              const Padding(
                padding: EdgeInsets.all(8),
                child: Text('J.A.R.V.I.S / ЦЕНТР УПРАВЛЕНИЯ',
                  style: TextStyle(color: kCyan, fontWeight: FontWeight.bold, letterSpacing: 1)),
              ),
              const Divider(color: kCyan),
              ListTile(
                leading: const Icon(Icons.dashboard, color: kCyan),
                title: const Text('Главный экран'),
                onTap: () => Navigator.pop(context),
              ),
              ExpansionTile(
                leading: const Icon(Icons.currency_bitcoin, color: kCyan),
                title: const Text('Криптовалюта'),
                subtitle: const Text('Все криптоинструменты в одной папке'),
                children: [
                  _menuItem(Icons.trending_up, 'Цены и рынки', () => _openMenuScreen(const JarvisCryptoScreen())),
                  _menuItem(Icons.candlestick_chart, 'Графики и свечи', () => _openMenuScreen(const JarvisCryptoScreen())),
                  _menuItem(Icons.analytics, 'RSI / SMA · теханализ', () => _openMenuScreen(const JarvisCryptoScreen())),
                  _menuItem(Icons.show_chart, 'Funding / Open Interest', () => _openMenuScreen(const JarvisCryptoScreen())),
                  _menuItem(Icons.query_stats, 'Ликвидации · CVD · Long/Short · CoinGlass', () => _openMenuScreen(const JarvisCryptoScreen())),
                ],
              ),
              ExpansionTile(
                leading: const Icon(Icons.travel_explore, color: kCyan),
                title: const Text('OSINT-разведка'),
                subtitle: const Text('Все проверки открытых источников'),
                children: [
                  _menuItem(Icons.language, 'Домен · DNS · RDAP', () => _openMenuScreen(const JarvisOsintScreen())),
                  _menuItem(Icons.router, 'IP · ASN · география', () => _openMenuScreen(const JarvisOsintScreen())),
                  _menuItem(Icons.link, 'URL · HTTP · TLS', () => _openMenuScreen(const JarvisOsintScreen())),
                  _menuItem(Icons.alternate_email, 'Email · username', () => _openMenuScreen(const JarvisOsintScreen())),
                  _menuItem(Icons.image_search, 'Метаданные изображения', () => _openMenuScreen(const JarvisOsintScreen())),
                ],
              ),
              ExpansionTile(
                leading: const Icon(Icons.memory, color: kCyan),
                title: const Text('Система и диагностика'),
                children: [
                  _menuItem(Icons.monitor_heart, 'Статус JARVIS', () => _openMenuScreen(const JarvisSystemScreen())),
                  _menuItem(Icons.speed, 'Проверить подключение AI', () => _connectAndroid()),
                  _menuItem(Icons.settings, 'Настройки AI и API', () => _settings()),
                ],
              ),
              ExpansionTile(
                leading: const Icon(Icons.folder, color: kCyan),
                title: const Text('Файлы и приложения'),
                children: [
                  _menuItem(Icons.search, 'Выбрать и просмотреть файлы', () => _openMenuScreen(const JarvisFilesScreen())),
                  _menuItem(Icons.folder_open, 'Открыть системный выбор файлов', () => _openMenuScreen(const JarvisFilesScreen())),
                  _menuItem(Icons.apps, 'Команда AI: запуск приложения', () => _sendFromMenu('Можно ли запустить приложение на Android? Если нет доступа к запуску приложений, честно сообщи об ограничении.')),
                ],
              ),
              ExpansionTile(
                leading: const Icon(Icons.mic, color: kCyan),
                title: const Text('Голос'),
                children: [
                  _menuItem(Icons.mic, 'Включить / выключить микрофон', _toggleVoice),
                  _menuItem(Icons.tune, 'Настройки микрофона', _showVoiceSettings),
                  _menuItem(Icons.volume_up, 'Озвучивание ответа', () => _sendFromMenu('Проверь озвучивание ответа')),
                ],
              ),
              ExpansionTile(
                leading: const Icon(Icons.public, color: kCyan),
                title: const Text('Интернет и информация'),
                children: [
                  _menuItem(Icons.travel_explore, 'Поиск в интернете', () => _openMenuScreen(const JarvisInternetScreen())),
                  _menuItem(Icons.cloud, 'Погода на 3 дня', () => _openMenuScreen(const JarvisInternetScreen())),
                  _menuItem(Icons.calculate, 'Калькулятор', () => _openMenuScreen(const JarvisCalculatorScreen())),
                  _menuItem(Icons.access_time, 'Дата и время', () => _openMenuScreen(const JarvisSystemScreen())),
                ],
              ),
              ExpansionTile(
                leading: const Icon(Icons.content_paste, color: kCyan),
                title: const Text('Буфер обмена'),
                children: [
                  _menuItem(Icons.content_paste, 'Читать и записывать текст', () => _openMenuScreen(const JarvisClipboardScreen())),
                ],
              ),
              ExpansionTile(
                leading: const Icon(Icons.psychology, color: kCyan),
                title: const Text('Память и задачи'),
                children: [
                  _menuItem(Icons.bookmark_add, 'Заметки и память', () => _openMenuScreen(const JarvisMemoryScreen())),
                  _menuItem(Icons.alarm, 'Напоминания и таймеры', () => _openMenuScreen(const JarvisMemoryScreen())),
                  _menuItem(Icons.hub, 'Граф знаний — AI-запрос', () => _sendFromMenu('Покажи граф знаний')),
                ],
              ),
            ],
          ),
        ),
      ) : null,
      body: _mainContent(),
    );
  }

  Widget _mainContent({bool compact = false}) => Column(children: [
        SizedBox(height: compact ? 30 : 38, child: ListView(scrollDirection: Axis.horizontal, padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3), children: [
          _hudPill('CORE', _busy ? 'THINKING' : 'ONLINE', _busy ? Colors.amberAccent : kCyan),
          _hudPill('AI', _jarvis == null ? 'DISCONNECTED' : 'CONNECTED', _jarvis == null ? Colors.redAccent : Colors.lightGreenAccent),
          _hudPill('VOICE', _voiceRunning ? 'LISTENING' : (_voiceReady ? 'READY' : 'STANDBY'), _voiceRunning ? Colors.greenAccent : Colors.white54),
          _hudPill('CRYPTO', 'OKX PUBLIC DATA', kCyan),
        ])),
        Container(height: compact ? 120 : 175, margin: const EdgeInsets.fromLTRB(10, 3, 10, 4), decoration: BoxDecoration(color: const Color(0xFF050912), border: Border.all(color: kCyan.withValues(alpha: .25)), borderRadius: BorderRadius.circular(14), boxShadow: [BoxShadow(color: kCyan.withValues(alpha: .06), blurRadius: 22)]), child: Stack(children: [
          Positioned.fill(child: JarvisReactor(color: switch (_visualState) { JarvisVisualState.listening => Colors.greenAccent, JarvisVisualState.thinking => Colors.amberAccent, JarvisVisualState.speaking => Colors.cyanAccent, JarvisVisualState.confirmation => Colors.lightGreenAccent, JarvisVisualState.error => Colors.redAccent, _ => kCyan }, state: _visualState)),
          const Positioned(top: 10, left: 12, child: Text('J.A.R.V.I.S', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w800, letterSpacing: 3, fontSize: 12))),
          Positioned(top: 10, right: 12, child: Text('LIVE NEURAL CORE', style: TextStyle(color: kCyan.withValues(alpha: .8), fontSize: 8, letterSpacing: 1.2))),
          Positioned(bottom: 10, left: 12, right: 12, child: Column(mainAxisSize: MainAxisSize.min, children: [
            Text('NEURAL NETWORK', style: TextStyle(color: kCyan.withValues(alpha: .85), fontSize: 10, letterSpacing: 3)),
            const SizedBox(height: 3),
            Text(switch (_visualState) { JarvisVisualState.listening => 'СЛУШАЮ', JarvisVisualState.thinking => 'ОБРАБАТЫВАЮ ЗАПРОС', JarvisVisualState.speaking => 'ОТВЕЧАЮ', JarvisVisualState.confirmation => 'ГОТОВО', JarvisVisualState.error => 'ОШИБКА', _ => 'СИСТЕМА ОЖИДАЕТ' }, style: const TextStyle(color: Colors.white70, fontSize: 9, letterSpacing: 2)),
          ])),
        ])),
        if (_showCryptoDashboard) ...[
          Padding(padding: const EdgeInsets.fromLTRB(10, 6, 10, 2), child: Row(children: [
            const Expanded(child: Text('КРИПТОЦЕНТР · РАБОЧАЯ ПАНЕЛЬ', style: TextStyle(color: kCyan, fontSize: 11, letterSpacing: 1, fontWeight: FontWeight.bold))),
            TextButton(onPressed: () => setState(() => _showCryptoDashboard = false), child: const Text('Скрыть')),
          ])),
          SizedBox(height: compact ? 160 : 220, child: const JarvisCryptoScreen()),
        ],
        Expanded(flex: 3, child: ListView.builder(controller: _scroll, padding: const EdgeInsets.all(16), itemCount: _messages.length + (_streamText.isNotEmpty ? 1 : 0), itemBuilder: (context, index) {
          if (_streamText.isNotEmpty && index == _messages.length) return Align(alignment: Alignment.centerLeft, child: Text(_streamText, style: TextStyle(fontSize: compact ? 15 : 17, height: 1.35)));
          final m = _messages[index];
          return Align(alignment: m.isUser ? Alignment.centerRight : Alignment.centerLeft, child: Container(margin: const EdgeInsets.only(bottom: 10), padding: const EdgeInsets.all(12), decoration: BoxDecoration(color: m.isUser ? kPanel : kBg, borderRadius: BorderRadius.circular(12), border: Border.all(color: kCyan.withValues(alpha: 0.25))), child: Row(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [Flexible(child: SelectableText(m.text, style: TextStyle(fontSize: compact ? 15 : 17, height: 1.35))), if (!m.isUser) IconButton(onPressed: () { Clipboard.setData(ClipboardData(text: m.text)); setState(() => _status = 'Текст скопирован'); }, icon: const Icon(Icons.copy, size: 18))])));
        })),
        if (_android && _heardText.isNotEmpty) Padding(padding: const EdgeInsets.symmetric(horizontal: 12), child: Text('🎙 $_heardText', maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 11))),
        Padding(padding: const EdgeInsets.fromLTRB(12, 4, 12, 12), child: Row(children: [
          Expanded(child: TextField(controller: _input, minLines: 2, maxLines: 4, textInputAction: TextInputAction.newline, onSubmitted: _send, decoration: const InputDecoration(hintText: 'Введите команду или вопрос…', border: OutlineInputBorder()))),
          if (_android) IconButton(
            tooltip: _voiceRunning ? 'Остановить голос' : 'Включить голос',
            onPressed: _busy ? null : _toggleVoice,
            icon: Icon(_voiceRunning ? Icons.mic_off : Icons.mic, color: kCyan),
          ),
          IconButton(onPressed: _busy ? null : () => _send(_input.text), icon: const Icon(Icons.send)),
        ])),
        Padding(padding: const EdgeInsets.only(bottom: 10), child: Text(_status, style: const TextStyle(fontSize: 12))),
      ]);

}

class JarvisHomePage extends StatefulWidget {
  const JarvisHomePage({super.key});
  @override
  State<JarvisHomePage> createState() => _JarvisHomePageState();
}
