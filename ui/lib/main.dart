// Busya Android UI/voice validation build
// Android terminal-launcher skin inspired by the linked Jarvis/Aris visual language.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:file_selector/file_selector.dart';
import 'jarvis_client.dart';

const kCyan = Color(0xFF32E6D0);
const kGreen = Color(0xFF35F58A);
const kRed = Color(0xFFFF5268);
const kAmber = Color(0xFFFFC857);
const kBg = Color(0xFF020607);
const kPanel = Color(0xFF071012);
const kLine = Color(0xFF17463F);
const _defaultAiEndpoint = 'https://openrouter.ai/api/v1';
const _defaultModel1 = 'openrouter/free';
const _defaultModel2 = 'deepseek/deepseek-v4-flash:free';
const _defaultModel3 = 'z-ai/glm-5.3-flash:free';

void main() => runApp(const BusyaApp());

class BusyaApp extends StatelessWidget {
  const BusyaApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'БУСЯ', debugShowCheckedModeBanner: false,
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
  static const _voice = MethodChannel('busya.voice');
  static const _voiceEvents = EventChannel('busya.voice.events');
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
  late final AnimationController _orbController;
  String _status = 'БУСЯ запускается…', _streamText = '';
  bool get _android => Platform.isAndroid;

  @override void initState() {
    super.initState();
    _orbController = AnimationController(vsync: this, duration: const Duration(seconds: 7))..repeat();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (_android) {
        await _loadSettings();
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
    if (value == '__READY__') { _voiceReady = true; _listening = false; setState(() => _status = 'Постоянный локальный голос'); await _startNativeListening(); return; }
    if (value == '__TTS_READY__') { if (mounted) setState(() => _status = 'Локальный русский голос готов'); return; }
    if (value == '__LOADING_VOICE__') { if (mounted) setState(() => _status = 'Загрузка локальной модели речи…'); return; }
    if (value.startsWith('__PARTIAL__:')) { if (mounted) setState(() => _status = 'Слышу: ${value.substring(12)}'); return; }
    if (value.startsWith('__TTS_ERROR__')) { if (mounted) setState(() => _status = 'Ошибка TTS: ${value.substring(12)}'); return; }
    if (value == '__MIC_SOURCE_READY__') { if (mounted) setState(() => _status = 'Микрофон подключён · проверяю сигнал…'); return; }
    if (value.startsWith('__MIC_LEVEL__:')) { if (mounted) setState(() => _status = 'Микрофон работает · сигнал ${value.substring(14)}'); return; }
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
    _listening = false;
    await _stopNativeListening();
    final phrase = value.trim();
    final command = phrase;
    _awaitingCommand = false;
    if (command.isEmpty) { Future<void>.delayed(const Duration(milliseconds: 300), () { if (mounted) _startNativeListening(); }); return; }
    if (mounted) setState(() => _status = 'Команда: $command');
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
    final key = _activeModel == 0 ? _key1.text.trim() : _activeModel == 1 ? _key2.text.trim() : _key3.text.trim();
    if (endpoint.isEmpty) { if (mounted) setState(() => _status = 'Укажите endpoint AI в настройках'); return; }
    try {
      final old = _client; _client = null; await old?.dispose();
      _client = await JarvisIpc.connectAi(endpoint, apiKey: key, model: model);
      await _finishConnect();
    } catch (e) { if (mounted) setState(() => _status = 'Ошибка подключения AI: $e'); }
  }

  Future<void> _finishConnect() async {
    final client = _client; if (client == null) return;
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
                const Text('У каждого профиля свой OpenRouter API key. Ключи сохраняются отдельно на телефоне.', style: TextStyle(color: Colors.white60, fontSize: 11)),
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
    setState(() { _busy = true; _streamText = ''; _messages.add(_Msg(attachment == null ? clean : '$clean\n📎 ${attachment.name}', isUser: true)); }); _scrollToBottom();
    try {
      final reply = await client.sendMessage(clean, attachment: attachment == null ? null : {'name': attachment.name, 'mime': attachment.mime, 'data': attachment.data});
      if (!mounted) return;
      setState(() { _messages.add(_Msg(reply.text, isUser: false)); _status = reply.needsConfirmation ? 'Требуется подтверждение' : (_android ? 'Локальное голосовое общение' : 'Готов'); });
      _scrollToBottom();
      if (_android && fromVoice) await _speak(reply.text);
    } catch (e) {
      if (!mounted) return;
      setState(() { _messages.add(_Msg('Ошибка: $e', isUser: false)); _status = 'Ошибка'; });
      if (_android && _voiceEnabled) await _speak('Произошла ошибка');
    } finally { if (mounted) setState(() => _busy = false); }
  }

  void _scrollToBottom() { WidgetsBinding.instance.addPostFrameCallback((_) { if (_scroll.hasClients) _scroll.animateTo(_scroll.position.maxScrollExtent, duration: const Duration(milliseconds: 180), curve: Curves.easeOut); }); }

  @override void dispose() {
    _orbController.dispose();
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
    return AnimatedBuilder(
      animation: _orbController,
      builder: (context, child) {
        final phase = _orbController.value * 6.283185307;
        final pulse = 0.92 + 0.08 * (0.5 + 0.5 * math.sin(phase));
        return Container(
      height: 250,
      margin: const EdgeInsets.fromLTRB(12, 12, 12, 8),
      decoration: BoxDecoration(
        gradient: const RadialGradient(
          center: Alignment.center,
          radius: 0.95,
          colors: [Color(0xFF123A35), Color(0xFF071A18), Color(0xFF030809)],
          stops: [0.0, 0.48, 1.0],
        ),
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: accent.withOpacity(.42)),
        boxShadow: [BoxShadow(color: accent.withOpacity(.10), blurRadius: 30, spreadRadius: 1)],
      ),
      child: Stack(
        alignment: Alignment.center,
        children: [
          for (final size in [210.0 * pulse, 170.0 * pulse, 132.0 * pulse])
            Container(
              width: size,
              height: size,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(color: accent.withOpacity(.10), width: 1),
              ),
            ),
          Container(
            width: 108 * pulse,
            height: 108 * pulse,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: RadialGradient(colors: [accent.withOpacity(.20), const Color(0xFF071311)]),
              border: Border.all(color: accent, width: 2),
              boxShadow: [BoxShadow(color: accent.withOpacity(.22), blurRadius: 28)],
            ),
            child: Icon(listening ? Icons.graphic_eq_rounded : Icons.auto_awesome, size: 46, color: accent),
          ),
          Positioned(
            top: 16,
            left: 18,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: const [
              Text('БУCЯ', style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w800, letterSpacing: 1.5)),
              SizedBox(height: 2),
              Text('JARVIS ASSISTANT', style: TextStyle(color: Colors.white54, fontSize: 9, letterSpacing: 1.8)),
            ]),
          ),
          Positioned(
            top: 18,
            right: 16,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: accent.withOpacity(.10),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: accent.withOpacity(.38)),
              ),
              child: Text(
                listening ? 'СЛУШАЮ' : (ready ? 'ГОТОВА' : 'МИКРОФОН ВЫКЛ'),
                style: TextStyle(color: accent, fontSize: 9, fontWeight: FontWeight.w800, letterSpacing: 1),
              ),
            ),
          ),
          Positioned(
            bottom: 16,
            left: 18,
            right: 18,
            child: Text(_status, maxLines: 2, overflow: TextOverflow.ellipsis, textAlign: TextAlign.center, style: const TextStyle(color: Colors.white70, fontSize: 11)),
          ),
        ],
      ),
    );
      },
    );
  }

  Widget _quickAction(IconData icon, String label, VoidCallback onTap) => Expanded(
    child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 3),
      child: OutlinedButton.icon(
        onPressed: onTap,
        icon: Icon(icon, size: 16),
        label: Text(label, style: const TextStyle(fontSize: 10)),
        style: OutlinedButton.styleFrom(
          foregroundColor: kCyan,
          side: const BorderSide(color: kLine),
          padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 5),
        ),
      ),
    ),
  );

  Widget _statusCard(IconData icon, String title, String value, Color color) {
    return Expanded(
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 4),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: kPanel,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: color.withOpacity(.18)),
        ),
        child: Row(children: [
          Icon(icon, color: color, size: 21),
          const SizedBox(width: 9),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: const TextStyle(color: Colors.white54, fontSize: 9)),
            const SizedBox(height: 2),
            Text(value, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w700)),
          ])),
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final micColor = _listening ? kGreen : (_voiceReady && _voiceEnabled ? kCyan : kRed);
    final modelLabel = (_activeModel + 1).toString() + '/3';
    return Scaffold(
      backgroundColor: kBg,
      body: SafeArea(
        child: Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 10, 10, 4),
            child: Row(children: [
              Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: const RadialGradient(colors: [Color(0xFF17463F), Color(0xFF07110F)]),
                  border: Border.all(color: kCyan.withOpacity(.45)),
                ),
                child: const Icon(Icons.auto_awesome, color: kCyan, size: 23),
              ),
              const SizedBox(width: 11),
              const Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('JARVIS', style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w800, letterSpacing: 1.6)),
                Text('БУCЯ · ЛИЧНЫЙ АССИСТЕНТ', style: TextStyle(color: Colors.white54, fontSize: 8, letterSpacing: 1.1)),
              ])),
              IconButton(tooltip: 'Микрофон', onPressed: _toggleVoice, icon: Icon(_listening ? Icons.mic_rounded : Icons.mic_none_rounded, color: micColor, size: 27)),
              IconButton(tooltip: 'Центр управления', onPressed: _settings, icon: const Icon(Icons.settings_rounded, color: kCyan, size: 25)),
            ]),
          ),
          _coreVisual(),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            child: Row(children: [
              _statusCard(Icons.memory_rounded, 'МОДЕЛЬ', modelLabel, kCyan),
              _statusCard(Icons.mic_rounded, 'STT', _voiceReady ? 'SHERPA · RU' : 'OFFLINE', kGreen),
              _statusCard(Icons.volume_up_rounded, 'TTS', _voiceReady ? 'PIPER · RU' : 'OFFLINE', kAmber),
            ]),
          ),
          Expanded(
            child: Container(
              margin: const EdgeInsets.fromLTRB(12, 8, 12, 4),
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 6),
              decoration: BoxDecoration(color: const Color(0xFF050C0C), borderRadius: BorderRadius.circular(20), border: Border.all(color: kLine.withOpacity(.8))),
              child: ListView(
                controller: _scroll,
                children: [
                  Row(children: [
                    const Expanded(child: Text('ДИАЛОГ', style: TextStyle(color: Colors.white60, fontSize: 10, fontWeight: FontWeight.w700, letterSpacing: 1))),
                    if (_busy) const SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 1.5, color: kCyan)),
                  ]),
                  const SizedBox(height: 8),
                  ..._messages.map((m) => Align(
                    alignment: m.isUser ? Alignment.centerRight : Alignment.centerLeft,
                    child: Container(
                      constraints: const BoxConstraints(maxWidth: 330),
                      margin: const EdgeInsets.only(bottom: 8),
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      decoration: BoxDecoration(
                        color: m.isUser ? const Color(0xFF0B2926) : const Color(0xFF0A1514),
                        borderRadius: BorderRadius.only(
                          topLeft: const Radius.circular(15),
                          topRight: const Radius.circular(15),
                          bottomLeft: Radius.circular(m.isUser ? 15 : 4),
                          bottomRight: Radius.circular(m.isUser ? 4 : 15),
                        ),
                        border: Border.all(color: (m.isUser ? kCyan : kGreen).withOpacity(.16)),
                      ),
                      child: Text(m.text, style: TextStyle(color: m.isUser ? Colors.white : Colors.white70, fontSize: 13, height: 1.3)),
                    ),
                  )),
                  if (_streamText.isNotEmpty) Text(_streamText, style: const TextStyle(color: kCyan, fontSize: 13)),
                  if (_messages.isEmpty && _streamText.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 34),
                      child: Center(child: Text('Готова к работе. Говорите или напишите команду.', textAlign: TextAlign.center, style: TextStyle(color: Colors.white38, fontSize: 12))),
                    ),
                  if (_attachment != null) Row(children: [
                    const Icon(Icons.attach_file_rounded, color: kCyan, size: 17),
                    const SizedBox(width: 5),
                    Expanded(child: Text(_attachment!.name, style: const TextStyle(color: kCyan, fontSize: 11))),
                    IconButton(icon: const Icon(Icons.close, color: kRed, size: 18), onPressed: () => setState(() => _attachment = null)),
                  ]),
                ],
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(10, 4, 10, 9),
            child: Row(children: [
              IconButton(onPressed: _busy ? null : _pickFile, icon: const Icon(Icons.attach_file_rounded, color: kCyan)),
              Expanded(
                child: TextField(
                  controller: _input,
                  textInputAction: TextInputAction.send,
                  onSubmitted: (value) { _input.clear(); _send(value); },
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                  cursorColor: kCyan,
                  decoration: InputDecoration(
                    hintText: 'Сообщение Бусе…',
                    hintStyle: const TextStyle(color: Colors.white30),
                    filled: true,
                    fillColor: kPanel,
                    contentPadding: const EdgeInsets.symmetric(horizontal: 15, vertical: 13),
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(18), borderSide: BorderSide(color: kLine.withOpacity(.8))),
                    enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(18), borderSide: BorderSide(color: kLine.withOpacity(.8))),
                    focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(18), borderSide: const BorderSide(color: kCyan)),
                  ),
                ),
              ),
              const SizedBox(width: 6),
              IconButton.filled(
                onPressed: _busy ? null : () { final text = _input.text; _input.clear(); _send(text); },
                style: IconButton.styleFrom(backgroundColor: const Color(0xFF0A2724), foregroundColor: kGreen),
                icon: const Icon(Icons.arrow_upward_rounded),
              ),
            ]),
          ),
        ]),
      ),
    );
  }

}
