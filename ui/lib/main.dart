// Busya Android UI/voice validation build
// Android CI rebuild: OpenRouter fallback + model display fix
// Analyzer fix: model label + response model scope
// Final CI source cleanup
// Android terminal-launcher skin inspired by the linked Jarvis/Aris visual language.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:file_selector/file_selector.dart';
import 'jarvis_ai_client.dart';
import 'jarvis_reactor.dart';

const kCyan = Color(0xFF08E6FF);
const kGreen = Color(0xFF45F0B0);
const kRed = Color(0xFFFF6078);
const kAmber = Color(0xFFFFC857);
const kBg = Color(0xFF070B12);
const kPanel = Color(0xFF0B111B);
const kLine = Color(0xFF18283A);
const _defaultAiEndpoint = 'https://openrouter.ai/api/v1';
const _defaultModel1 = 'openrouter/free';
const _defaultModel2 = 'qwen/qwen3.8-27b:free';
const _defaultModel3 = 'google/gemma-4-26b-a4b-it:free';

void main() => runApp(const BusyaApp());

class BusyaApp extends StatelessWidget {
  const BusyaApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'JARVIS', debugShowCheckedModeBanner: false,
    theme: ThemeData(brightness: Brightness.dark, scaffoldBackgroundColor: kBg,
      colorScheme: ColorScheme.fromSeed(seedColor: kCyan, brightness: Brightness.dark), useMaterial3: true,
      inputDecorationTheme: const InputDecorationTheme(filled: true, fillColor: Color(0xFF050B0C), border: OutlineInputBorder(borderSide: BorderSide(color: kLine)), enabledBorder: OutlineInputBorder(borderSide: BorderSide(color: kLine)), focusedBorder: OutlineInputBorder(borderSide: BorderSide(color: kCyan))) ),
    home: const BusyaHomePage(),
  );
}

class _Msg { _Msg(this.text, {required this.isUser}); final String text; final bool isUser; }
class _Attachment {
  _Attachment({required this.name, required this.mime, required this.data});
  final String name, mime, data;
}

class BusyaHomePage extends StatefulWidget {
  const BusyaHomePage({super.key});
  @override State<BusyaHomePage> createState() => _BusyaHomePageState();
}

class _BusyaHomePageState extends State<BusyaHomePage> with SingleTickerProviderStateMixin {
  static const _voice = MethodChannel('jarvis.voice');
  static const _voiceEvents = EventChannel('jarvis.voice.events');
  JarvisIpc? _client;
  final _input = TextEditingController(), _endpoint = TextEditingController(text: _defaultAiEndpoint),
      _model1 = TextEditingController(text: _defaultModel1), _model2 = TextEditingController(text: _defaultModel2), _model3 = TextEditingController(text: _defaultModel3),
      _key1 = TextEditingController(), _key2 = TextEditingController(), _key3 = TextEditingController(), _apiHostKey = TextEditingController();
  int _activeModel = 0;
  final _scroll = ScrollController();
  final _messages = <_Msg>[];
  _Attachment? _attachment;
  StreamSubscription<dynamic>? _voiceSub;
  StreamSubscription<String>? _partialSub;
  bool _voiceReady = false, _listening = false, _voiceEnabled = true, _awaitingCommand = false, _busy = false;
  // Русская модель распознавания пишет «Джарвис» по-разному, поэтому принимаем варианты.
  static final RegExp _jarvisWake = RegExp(r'^\s*(?:jarvis|jarvice|джарвис|джарвиз|джарвес|джервис|жарвис|жарвез|чарвис|харвис|джа\s?рвис|дж[ае]рв[иеы]с)\s*[,;:.!?-]?\s*', caseSensitive: false, unicode: true);
  // После обращения «Jarvis» или ответа ассистента команды принимаются без повторного обращения.
  static const Duration _conversationWindow = Duration(seconds: 20);
  DateTime _wakeUntil = DateTime.fromMillisecondsSinceEpoch(0);
  final ValueNotifier<double> _micLevel = ValueNotifier<double>(0);
  bool _speaking = false;
  // Внешний вид, которым Jarvis управляет сам через ui_* инструменты.
  double _uiHue = 0, _uiTextScale = 1.0, _uiOrbHeight = 286;
  bool _wakeRequired = false;
  static const Map<String, double> _hueByName = {
    'красный': 0, 'оранжевый': 28, 'жёлтый': 50, 'желтый': 50, 'золотой': 45, 'зелёный': 125, 'зеленый': 125,
    'бирюзовый': 186, 'голубой': 200, 'синий': 220, 'фиолетовый': 270, 'пурпурный': 300, 'розовый': 320,
    'red': 0, 'orange': 28, 'yellow': 50, 'gold': 45, 'green': 125, 'cyan': 186, 'blue': 220, 'purple': 270, 'pink': 320,
  };
  late final AnimationController _orbController;
  String _status = 'JARVIS запускается…', _streamText = '';
  bool get _android => Platform.isAndroid;

  @override void initState() {
    super.initState();
    _orbController = AnimationController(vsync: this, duration: const Duration(seconds: 7))..repeat();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (_android) {
        await _loadSettings();
        await _loadUi();
        await _connectAndroid();
        if (!mounted) return;
        await Future<void>.delayed(const Duration(milliseconds: 700));
        if (mounted && _voiceEnabled) await _initNativeVoice();
      } else {
        await _connectDesktop();
      }
    });
  }

  Future<void> _loadSettings() async {
    if (!_android) return;
    try {
      final raw = await _voice.invokeMethod<dynamic>('load_settings');
      if (raw is Map) {
        final endpoint = raw['endpoint']?.toString().trim() ?? '';
        final model = raw['model']?.toString().trim() ?? '';
        final apiKey = raw['apiKey']?.toString() ?? '';
        final apiHostKey = raw['apiHostKey']?.toString() ?? '';
        final model1 = raw['model1']?.toString().trim() ?? '';
        final model2 = raw['model2']?.toString().trim() ?? '';
        final model3 = raw['model3']?.toString().trim() ?? '';
        final key1 = raw['key1']?.toString() ?? '';
        final key2 = raw['key2']?.toString() ?? '';
        final key3 = raw['key3']?.toString() ?? '';
        final activeModel = raw['activeModel'];
        final voiceEnabled = raw['voiceEnabled'];
        if (endpoint.isNotEmpty) _endpoint.text = endpoint;
        if (model1.isNotEmpty) _model1.text = model1; else if (model.isNotEmpty) _model1.text = model;
        if (model2.isNotEmpty) _model2.text = model2;
        if (model3.isNotEmpty) _model3.text = model3;
        _key1.text = key1.isNotEmpty ? key1 : apiKey;
        _key2.text = key2;
        _key3.text = key3;
        _apiHostKey.text = apiHostKey;
        if (activeModel is int && activeModel >= 0 && activeModel <= 2) _activeModel = activeModel;
        if (voiceEnabled is bool) _voiceEnabled = voiceEnabled;
      }
    } catch (_) {}
  }

  Future<void> _pickFile() async {
    try {
      const typeGroup = XTypeGroup(
        label: 'Файлы',
        extensions: <String>[
          'txt', 'md', 'csv', 'json', 'xml', 'log',
          'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
          'jpg', 'jpeg', 'png', 'webp', 'gif',
          'mp3', 'wav', 'm4a', 'ogg', 'webm', 'aac',
        ],
      );
      final file = await openFile(acceptedTypeGroups: <XTypeGroup>[typeGroup]);
      if (file == null) return;
      final bytes = await file.readAsBytes();
      if (bytes.isEmpty) throw StateError('Файл пустой');
      final mime = file.mimeType ?? 'application/octet-stream';
      if (bytes.length > 25 * 1024 * 1024) {
        throw StateError('Файл слишком большой. Максимальный размер — 25 МБ.');
      }
      if (mounted) setState(() {
        _attachment = _Attachment(name: file.name, mime: mime, data: base64Encode(bytes));
        _status = 'Файл прикреплён: ${file.name}';
      });
    } catch (e) {
      if (mounted) setState(() => _status = 'Ошибка выбора файла: $e');
    }
  }

  Future<void> _saveSettings() async {
    if (!_android) return;
    try {
      await _voice.invokeMethod('save_settings', {
        'endpoint': _endpoint.text.trim(),
        'model': _activeModel == 0 ? _model1.text.trim() : _activeModel == 1 ? _model2.text.trim() : _model3.text.trim(),
        'apiKey': _activeModel == 0 ? _key1.text.trim() : _activeModel == 1 ? _key2.text.trim() : _key3.text.trim(),
        'model1': _model1.text.trim(), 'model2': _model2.text.trim(), 'model3': _model3.text.trim(),
        'key1': _key1.text.trim(), 'key2': _key2.text.trim(), 'key3': _key3.text.trim(),
        'activeModel': _activeModel,
        'apiHostKey': _apiHostKey.text.trim(),
        'voiceEnabled': _voiceEnabled,
      });
    } catch (_) {}
  }

  Future<void> _saveUi() async {
    if (!_android) return;
    try { await _voice.invokeMethod('save_ui', {'json': jsonEncode({'hue': _uiHue, 'text': _uiTextScale, 'orb': _uiOrbHeight, 'wake': _wakeRequired})}); } catch (_) {}
  }

  Future<void> _loadUi() async {
    if (!_android) return;
    try {
      final raw = await _voice.invokeMethod<String>('load_ui');
      if (raw == null || raw.isEmpty) return;
      final m = jsonDecode(raw);
      if (m is Map && mounted) {
        setState(() {
          _uiHue = (m['hue'] as num?)?.toDouble() ?? 0;
          _uiTextScale = (m['text'] as num?)?.toDouble() ?? 1.0;
          _uiOrbHeight = (m['orb'] as num?)?.toDouble() ?? 286;
          _wakeRequired = m['wake'] == true;
        });
      }
    } catch (_) {}
  }

  String _uiStateJson() => jsonEncode({'hue_shift': _uiHue, 'text_scale': _uiTextScale, 'orb_height': _uiOrbHeight, 'wake_word_required': _wakeRequired, 'voice_enabled': _voiceEnabled});

  Future<String> _uiTool(String name, Map<String, dynamic> a) async {
    String done(String message) => jsonEncode({'ok': true, 'message': message, 'state': jsonDecode(_uiStateJson())});
    if (name == 'ui_set_theme') {
      final raw = (a['color'] ?? a['accent'] ?? '').toString().trim().toLowerCase();
      double? target = _hueByName[raw];
      if (target == null) {
        final hex = raw.replaceFirst('#', '');
        if (RegExp(r'^[0-9a-f]{6}$').hasMatch(hex)) target = HSVColor.fromColor(Color(int.parse('FF$hex', radix: 16))).hue;
      }
      if (target == null) return jsonEncode({'ok': false, 'error': 'Неизвестный цвет: $raw. Назови цвет (красный, зелёный, синий, фиолетовый, оранжевый, розовый, жёлтый, бирюзовый) или #RRGGBB'});
      final shift = target - 186.0;
      if (mounted) setState(() => _uiHue = shift);
      await _saveUi();
      return done('Цвет интерфейса изменён');
    }
    if (name == 'ui_set_text_scale') {
      final v = ((a['scale'] as num?)?.toDouble() ?? 1.0).clamp(0.8, 1.6).toDouble();
      if (mounted) setState(() => _uiTextScale = v);
      await _saveUi();
      return done('Размер текста изменён');
    }
    if (name == 'ui_set_orb_height') {
      final v = ((a['height'] as num?)?.toDouble() ?? 286).clamp(160.0, 420.0).toDouble();
      if (mounted) setState(() => _uiOrbHeight = v);
      await _saveUi();
      return done('Размер ядра изменён');
    }
    if (name == 'ui_set_wake_word') {
      final v = a['required'] == true;
      if (mounted) setState(() => _wakeRequired = v);
      await _saveUi();
      return done(v ? 'Теперь команды только после слова Джарвис' : 'Теперь слушаю без слова Джарвис');
    }
    if (name == 'ui_set_voice') {
      final want = a['enabled'] != false;
      if (want != _voiceEnabled) await _toggleVoice();
      return done(want ? 'Голос включён' : 'Голос выключен');
    }
    if (name == 'ui_open_settings') {
      Future<void>.delayed(const Duration(milliseconds: 400), () { if (mounted) _settings(); });
      return done('Открываю настройки');
    }
    if (name == 'ui_reset') {
      if (mounted) setState(() { _uiHue = 0; _uiTextScale = 1.0; _uiOrbHeight = 286; _wakeRequired = false; });
      await _saveUi();
      return done('Внешний вид сброшен');
    }
    if (name == 'ui_get_state') return done('Текущее состояние');
    return jsonEncode({'ok': false, 'error': 'Неизвестная команда интерфейса: $name'});
  }

  Future<void> _initNativeVoice() async {
    if (!_android || !mounted) return;
    try {
      await _voiceSub?.cancel();
      _voiceSub = _voiceEvents.receiveBroadcastStream().listen(_onNativeVoiceEvent,
        onError: (Object e) { if (mounted) setState(() => _status = 'Ошибка голоса: $e'); });
      final available = await _voice.invokeMethod<bool>('initialize') ?? false;
      if (!mounted) return;
      if (!available) { setState(() => _status = 'Не удалось запустить голосовой модуль'); return; }
      setState(() => _status = 'Запрашиваю/запускаю микрофон…');
    } catch (e) { if (mounted) setState(() => _status = 'Ошибка голоса: $e'); }
  }

  Future<void> _startNativeListening() async {
    if (!_android || !_voiceReady || !_voiceEnabled || _busy || _listening) return;
    try {
      _listening = true;
      await _voice.invokeMethod('listen_now');
      if (mounted) setState(() => _status = 'Постоянное голосовое слушание');
    } catch (e) {
      _listening = false;
      if (mounted) setState(() => _status = 'Ошибка микрофона: $e');
    }
  }

  Future<void> _stopNativeListening() async {
    if (!_android) return;
    try { await _voice.invokeMethod('stop'); } catch (_) {}
    _listening = false;
  }

  Future<void> _onNativeVoiceEvent(dynamic event) async {
    if (!_android || !_voiceEnabled || !mounted) return;
    final value = event?.toString().trim() ?? '';
    if (value.isEmpty) return;
    if (value == '__READY__') { _voiceReady = true; _listening = false; if (mounted) setState(() => _status = 'Русский голосовой контур готов · слушаю'); return; }
    if (value == '__TTS_READY__') { if (mounted) setState(() => _status = 'Локальный русский голос готов'); return; }
    if (value == '__LOADING_VOICE__') { if (mounted) setState(() => _status = 'Загрузка локальной модели речи…'); return; }
    if (value.startsWith('__PARTIAL__:')) { if (mounted) setState(() => _status = 'Слышу: ${value.substring(12)}'); return; }
    if (value.startsWith('__TTS_ERROR__')) { if (mounted) setState(() => _status = 'Ошибка TTS: ${value.substring(12)}'); return; }
    if (value == '__MIC_SOURCE_READY__') { if (mounted) setState(() => _status = 'Микрофон подключён · проверяю сигнал…'); return; }
    if (value.startsWith('__MIC_LEVEL__:')) {
      // Уровень идёт только в анимацию (без setState), чтобы ядро реагировало на голос вживую.
      final rms = double.tryParse(value.substring(14)) ?? 0;
      _micLevel.value = (rms * 7).clamp(0.0, 1.0).toDouble();
      return;
    }
    if (value == '__TTS_START__') { _speaking = true; if (mounted) setState(() {}); return; }
    if (value == '__TTS_DONE__' || value == '__TTS_INTERRUPTED__') {
      _speaking = false;
      _wakeUntil = DateTime.now().add(_conversationWindow);
      if (mounted) setState(() {});
      return;
    }
    if (value == '__VAD_SPEECH_BEGIN__' || value == '__VAD_SPEECH_END__' || value == '__VAD_READY__') return;
    if (value == '__LISTENING__') { _listening = true; if (mounted) setState(() => _status = 'Слушаю…'); return; }
    if (value.startsWith('__ERROR__:')) {
      _listening = false;
      if (mounted) setState(() => _status = 'Ошибка голоса: ${value.substring(10)}');
      if (_voiceEnabled && !_busy) Future<void>.delayed(const Duration(milliseconds: 700), () { if (mounted) _startNativeListening(); });
      return;
    }
    if (value == '__END__') {
      _listening = false;
      if (_voiceEnabled && !_busy) Future<void>.delayed(const Duration(milliseconds: 450), () { if (mounted) _startNativeListening(); });
      return;
    }
    // Любые служебные события вида __NAME__ — не речь пользователя. Раньше они
    // попадали сюда и перезапускали микрофон посреди фразы.
    if (value.startsWith('__')) return;
    _listening = false;
    await _stopNativeListening();
    final phrase = value.trim();
    final wakeMatch = _jarvisWake.matchAsPrefix(phrase);
    if (mounted) setState(() => _status = 'Услышал: $phrase');
    // Голосовые команды принимаются только после обращения «Jarvis».
    // Никаких хлопков, порогов амплитуды или скрытой активации.
    final inWindow = DateTime.now().isBefore(_wakeUntil);
    if (_wakeRequired && wakeMatch == null && !inWindow) {
      if (mounted) setState(() => _status = 'Жду команду «Jarvis …»');
      Future<void>.delayed(const Duration(milliseconds: 120), () { if (mounted) _startNativeListening(); });
      return;
    }
    final command = wakeMatch == null ? phrase : phrase.substring(wakeMatch.end).trim();
    _wakeUntil = DateTime.now().add(_conversationWindow);
    _awaitingCommand = false;
    if (command.isEmpty) {
      if (mounted) setState(() => _status = 'Jarvis активирован · слушаю команду');
      Future<void>.delayed(const Duration(milliseconds: 120), () { if (mounted) _startNativeListening(); });
      return;
    }
    if (mounted) setState(() => _status = 'Команда Jarvis: $command');
    await _send(command, fromVoice: true);
  }

  Future<void> _speak(String text) async {
    if (!_android || !mounted || text.trim().isEmpty) return;
    try { await _voice.invokeMethod('speak', {'text': text.trim()}); } catch (_) {}
  }

  Future<void> _connectDesktop() async {
    try {
      final dir = File(Platform.resolvedExecutable).parent.path;
      final exe = '$dir${Platform.pathSeparator}jarvis.exe';
      _client = await (File(exe).existsSync() ? JarvisIpc.spawn(exe) : JarvisIpc.spawn('python', ['-m', 'agent', '--ipc']));
      await _finishConnect();
    } catch (e) { if (mounted) setState(() => _status = 'Агент не запущен: $e'); }
  }

  Future<void> _connectAndroid() async {
    await _saveSettings();
    final endpoint = _endpoint.text.trim();
    final model = _activeModel == 0 ? _model1.text.trim() : _activeModel == 1 ? _model2.text.trim() : _model3.text.trim();
    final selectedKey = _activeModel == 0 ? _key1.text.trim() : _activeModel == 1 ? _key2.text.trim() : _key3.text.trim();
    final key = selectedKey.isNotEmpty ? selectedKey : _key1.text.trim();
    if (endpoint.isEmpty) { if (mounted) setState(() => _status = 'Укажите endpoint AI в настройках'); return; }
    try {
      final old = _client; _client = null; await old?.dispose();
      if (key.isEmpty) throw StateError('API-ключ не указан для выбранной модели');
      String fallbackEndpoint = '';
      String fallbackKey = '';
      String fallbackModel = '';
      final host = Uri.tryParse(endpoint)?.host.toLowerCase() ?? '';
      if (host.contains('groq.com')) {
        fallbackEndpoint = 'https://api.cerebras.ai/v1';
        fallbackKey = _key2.text.trim();
        fallbackModel = _model2.text.trim();
      } else if (host.contains('cerebras.ai')) {
        fallbackEndpoint = 'https://api.groq.com/openai/v1';
        fallbackKey = _key1.text.trim();
        fallbackModel = _model1.text.trim();
      }
      _client = await JarvisIpc.connectAi(endpoint, apiKey: key, model: model,
        fallbackApiUrl: fallbackEndpoint, fallbackApiKey: fallbackKey, fallbackModel: fallbackModel);
      await _client!.verifyConnection();
      await _finishConnect();
    } catch (e) { if (mounted) setState(() => _status = 'Ошибка подключения AI: $e'); }
  }

  Future<void> _finishConnect() async {
    final client = _client; if (client == null) return;
    client.uiHandler = _uiTool;
    final tools = await client.listTools();
    await _partialSub?.cancel();
    _partialSub = client.partials().listen((text) { if (mounted) setState(() => _streamText = text); });
    if (mounted) setState(() => _status = _android ? 'AI подключён · постоянно слушаю' : 'Агент подключён · инструментов: ${tools.length}');
    if (_android && _voiceReady && _voiceEnabled) _startNativeListening();
  }

  Future<void> _settings() async {
    if (!_android) return;
    final previousVoiceEnabled = _voiceEnabled;
    var saved = false;
    _awaitingCommand = false;
    await _stopNativeListening();
    await showDialog<void>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: const Row(children: [Icon(Icons.tune, color: kCyan), SizedBox(width: 8), Text('ЦЕНТР УПРАВЛЕНИЯ')]),
          content: SizedBox(
            width: 520,
            child: SingleChildScrollView(
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                const Text('API / AI · 3 ПРОФИЛЯ', style: TextStyle(color: kCyan, fontWeight: FontWeight.bold)),
                const SizedBox(height: 4),
                const Text('Один OpenRouter API key можно использовать для всех трёх моделей. Если ключ профиля пуст, JARVIS использует API KEY 1.', style: TextStyle(color: Colors.white60, fontSize: 11)),
                const SizedBox(height: 8),
                for (int i = 0; i < 3; i++) ...[
                  Card(
                    color: _activeModel == i ? const Color(0xFF0A2421) : kPanel,
                    child: Padding(
                      padding: const EdgeInsets.all(8),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                        Row(children: [
                          Expanded(child: Text(i == 0 ? 'API KEY 1 · JARVIS' : i == 1 ? 'API KEY 2 · DEEPSEEK' : 'API KEY 3 · GLM', style: const TextStyle(color: kGreen, fontWeight: FontWeight.bold))),
                          Radio<int>(value: i, groupValue: _activeModel, onChanged: (v) { if (v != null) setDialogState(() => _activeModel = v); }),
                        ]),
                        TextField(controller: i == 0 ? _model1 : i == 1 ? _model2 : _model3, decoration: const InputDecoration(labelText: 'Model ID', isDense: true)),
                        const SizedBox(height: 6),
                        TextField(controller: i == 0 ? _key1 : i == 1 ? _key2 : _key3, obscureText: true, decoration: InputDecoration(labelText: 'OpenRouter API key ${i + 1}', hintText: 'sk-or-v1-…', isDense: true, prefixIcon: const Icon(Icons.key, size: 18, color: kCyan))),
                      ]),
                    ),
                  ),
                  const SizedBox(height: 6),
                ],
                TextField(controller: _endpoint, keyboardType: TextInputType.url, decoration: const InputDecoration(labelText: 'OpenRouter endpoint', isDense: true)),
                const SizedBox(height: 6),
                TextField(controller: _apiHostKey, obscureText: true, decoration: const InputDecoration(labelText: 'APIHOST key · голос Леда', isDense: true)),
                const SizedBox(height: 12),
                const Text('ГОЛОС / МИКРОФОН', style: TextStyle(color: kCyan, fontWeight: FontWeight.bold)),
                SwitchListTile(dense: true, contentPadding: EdgeInsets.zero, value: _voiceEnabled, onChanged: (v) => setDialogState(() => _voiceEnabled = v), title: const Text('Постоянно слушать микрофон'), subtitle: const Text('Локальный русский STT. Микрофон работает только при открытом приложении.')),
                const SizedBox(height: 12),
                const Text('ИНСТРУМЕНТЫ', style: TextStyle(color: kCyan, fontWeight: FontWeight.bold)),
                Wrap(spacing: 6, runSpacing: 6, children: [
                  _commandChip('help'), _commandChip('status'), _commandChip('voice'), _commandChip('settings'),
                  _commandChip('поиск'), _commandChip('погода'), _commandChip('список файлов'), _commandChip('покажи память'),
                  _commandChip('чему ты научилась'), _commandChip('самоулучшайся'),
                ]),
              ]),
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Закрыть')),
            FilledButton.icon(
              onPressed: () async {
                await _saveSettings();
                saved = true;
                if (ctx.mounted) Navigator.pop(ctx);
                await _connectAndroid();
                if (mounted) {
                  setState(() => _status = 'Центр управления сохранён · ' + (_activeModel + 1).toString() + '-я модель');
                  if (_voiceEnabled) await _startNativeListening();
                }
              },
              icon: const Icon(Icons.check),
              label: const Text('Сохранить и подключить'),
            ),
          ],
        ),
      ),
    );
    if (mounted && !saved) {
      _voiceEnabled = previousVoiceEnabled;
      if (_voiceEnabled && _voiceReady) {
        setState(() => _status = 'Постоянный локальный голос');
        await _startNativeListening();
      }
    } else if (mounted && _voiceReady && _voiceEnabled) {
      setState(() => _status = 'Постоянный локальный голос');
      await _startNativeListening();
    }
  }

  Future<void> _toggleVoice() async {
    if (!_android) return;
    if (!_voiceReady) { await _initNativeVoice(); return; }
    _voiceEnabled = !_voiceEnabled; _awaitingCommand = false; await _saveSettings();
    if (!_voiceEnabled) { await _stopNativeListening(); if (mounted) setState(() => _status = 'Голос выключен'); return; }
    if (mounted) setState(() => _status = 'Постоянный локальный голос'); await _startNativeListening();
  }

  Future<void> _send(String text, {bool fromVoice = false}) async {
    final clean = text.trim(); final client = _client; final attachment = _attachment;
    if (clean.isEmpty || _busy) return;
    if (client == null) { if (mounted) setState(() => _status = 'Сначала подключите AI в настройках'); if (fromVoice) await _speak('Сначала подключите AI в настройках'); return; }
    // Pause native STT during typed requests to avoid AudioRecord/Sherpa races.
    final resumeVoice = _android && _voiceEnabled && !fromVoice;
    if (resumeVoice) await _stopNativeListening();
    if (!mounted) return;
    setState(() { _busy = true; _streamText = ''; _messages.add(_Msg(attachment == null ? clean : '$clean\n📎 ${attachment.name}', isUser: true)); });
    _scrollToBottom();
    try {
      final reply = await client.sendMessage(clean, attachment: attachment == null ? null : {'name': attachment.name, 'mime': attachment.mime, 'data': attachment.data});
      if (!mounted) return;
      setState(() { _messages.add(_Msg(reply.text, isUser: false)); _status = reply.needsConfirmation ? 'Требуется подтверждение' : (_android ? 'JARVIS · голосовой канал' : 'Готов'); });
      _scrollToBottom();
      if (_android && _voiceEnabled) await _speak(reply.text);
    } catch (e) {
      if (!mounted) return;
      final errorText = e.toString();
      final userError = errorText.contains('AI 429:')
          ? 'Лимит основного AI исчерпан. JARVIS попытался перейти на резервный канал. Проверьте второй API-ключ и модель.'
          : errorText.contains('AI 401:')
              ? 'API-ключ отклонён. Проверьте ключ выбранной модели.'
              : errorText;
      setState(() { _messages.add(_Msg('Ошибка: $userError', isUser: false)); _status = errorText.contains('AI 429:') ? 'Лимит AI · резервный канал' : 'Ошибка'; });
      if (_android && _voiceEnabled) await _speak('Произошла ошибка');
    } finally {
      if (mounted) setState(() => _busy = false);
      if (resumeVoice && mounted && _voiceEnabled) {
        await Future<void>.delayed(const Duration(milliseconds: 250));
        if (mounted && !_busy) await _startNativeListening();
      }
    }
  }

  void _scrollToBottom() { WidgetsBinding.instance.addPostFrameCallback((_) { if (_scroll.hasClients) _scroll.animateTo(_scroll.position.maxScrollExtent, duration: const Duration(milliseconds: 180), curve: Curves.easeOut); }); }

  @override void dispose() {
    _orbController.dispose();
    _micLevel.dispose();
    _voiceSub?.cancel(); _partialSub?.cancel();
    if (_android) { _voice.invokeMethod('stop'); _voice.invokeMethod('dispose'); }
    _client?.dispose(); _input.dispose(); _endpoint.dispose(); _model1.dispose(); _model2.dispose(); _model3.dispose(); _key1.dispose(); _key2.dispose(); _key3.dispose(); _apiHostKey.dispose(); _scroll.dispose(); super.dispose();
  }

  Widget _terminalLine(String text, {Color color = kGreen, bool dim = false}) {
    return Padding(padding: const EdgeInsets.only(bottom: 3), child: Text(text, maxLines: 8, overflow: TextOverflow.ellipsis,
      style: TextStyle(color: dim ? color.withOpacity(.55) : color, fontSize: 12, height: 1.18, fontFamily: 'monospace')));
  }

  Widget _gauge(String value, String label, {Color color = kCyan}) {
    return Container(width: 76, height: 76, decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: color.withOpacity(.65), width: 1.5)),
      child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        Text(value, style: TextStyle(color: color, fontSize: 14, fontWeight: FontWeight.bold)),
        Text(label, style: TextStyle(color: color.withOpacity(.65), fontSize: 8)),
      ]));
  }

  Widget _commandChip(String text) => InkWell(
    onTap: _busy ? null : () async {
      await _send(text);
    },
    child: Container(padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration: BoxDecoration(color: kPanel, border: Border.all(color: kLine), borderRadius: BorderRadius.circular(3)),
      child: Text(text, style: const TextStyle(color: kCyan, fontSize: 10, fontFamily: 'monospace'))));

  Widget _coreVisual() {
    final listening = _listening;
    final ready = _voiceReady && _voiceEnabled;
    final accent = listening ? kGreen : (ready ? kCyan : kRed);
    final visualState = _speaking ? JarvisVisualState.speaking : _busy ? JarvisVisualState.thinking : listening ? JarvisVisualState.listening : JarvisVisualState.idle;
    return AnimatedBuilder(
      animation: _orbController,
      builder: (context, child) {
        return Container(
          height: _uiOrbHeight,
          margin: const EdgeInsets.fromLTRB(10, 10, 10, 6),
          decoration: BoxDecoration(
            color: const Color(0xFF080E17),
            border: Border.all(color: const Color(0xFF18283A)),
            borderRadius: BorderRadius.circular(8),
            boxShadow: [BoxShadow(color: Colors.black.withOpacity(.35), blurRadius: 24)],
          ),
          child: Stack(
            alignment: Alignment.center,
            children: [