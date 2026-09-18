import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:file_selector/file_selector.dart';
import 'package:record/record.dart';
import 'package:whisper_ggml/whisper_ggml.dart';
import 'jarvis_client.dart';

const kCyan = Color(0xFF37D5EE);
const kBg = Color(0xFF05080F);
const kPanel = Color(0xFF0D1622);
const _defaultAiEndpoint = 'https://openrouter.ai/api/v1';
const _defaultAiModel = 'openrouter/free';

void main() => runApp(const BusyaApp());

class BusyaApp extends StatelessWidget {
  const BusyaApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'БУСЯ', debugShowCheckedModeBanner: false,
    theme: ThemeData(brightness: Brightness.dark, scaffoldBackgroundColor: kBg,
      colorScheme: ColorScheme.fromSeed(seedColor: kCyan, brightness: Brightness.dark), useMaterial3: true),
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

class _BusyaHomePageState extends State<BusyaHomePage> {
  static const _voice = MethodChannel('busya.voice');
  static const _voiceEvents = EventChannel('busya.voice.events');
  JarvisIpc? _client;
  final _input = TextEditingController(), _endpoint = TextEditingController(text: _defaultAiEndpoint), _apiKey = TextEditingController(), _model = TextEditingController(text: _defaultAiModel), _apiHostKey = TextEditingController();
  final _scroll = ScrollController();
  final _messages = <_Msg>[];
  _Attachment? _attachment;
  StreamSubscription<dynamic>? _voiceSub;
  StreamSubscription<String>? _partialSub;
  StreamSubscription<Uint8List>? _pcmSub;
  final AudioRecorder _localRecorder = AudioRecorder();
  final WhisperController _whisper = WhisperController();
  WhisperLiveSession? _whisperSession;
  bool _localWhisperRunning = false;
  bool _localSpeechStarted = false;
  int _localSilenceMs = 0;
  int _localSpeechMs = 0;
  bool _voiceReady = false, _listening = false, _voiceEnabled = true, _awaitingCommand = false, _busy = false;
  String _status = 'БУСЯ запускается…', _streamText = '';
  bool get _android => Platform.isAndroid;

  @override void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (_android) {
        await _loadSettings();
        await _initNativeVoice();
        await _connectAndroid();
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
        final voiceEnabled = raw['voiceEnabled'];
        if (endpoint.isNotEmpty) _endpoint.text = endpoint;
        if (model.isNotEmpty) _model.text = model;
        _apiKey.text = apiKey;
        _apiHostKey.text = apiHostKey;
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
        'model': _model.text.trim(),
        'apiKey': _apiKey.text.trim(),
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
      if (!available) { setState(() => _status = 'Голосовой движок недоступен на Android'); return; }
      _voiceReady = true; _voiceEnabled = true;
      setState(() => _status = 'Голосовой режим: слушаю');
      await _armNativeWake();
    } catch (e) { if (mounted) setState(() => _status = 'Ошибка голоса: $e'); }
  }

  Future<void> _startNativeListening() async {
    if (!_android || !_voiceReady || !_voiceEnabled || _busy || _localWhisperRunning) return;
    await _startLocalWhisper();
  }

  Future<void> _armNativeWake() async {
    if (!_android || !_voiceReady || !_voiceEnabled || _busy) return;
    try { await _voice.invokeMethod('start'); }
    catch (e) { if (mounted) setState(() => _status = 'Ошибка пробуждения: $e'); }
  }

  Future<void> _startLocalWhisper() async {
    if (!_android || !_voiceReady || !_voiceEnabled || _busy || _localWhisperRunning) return;
    try {
      if (!await _localRecorder.hasPermission()) {
        if (mounted) setState(() => _status = 'Нет доступа к микрофону');
        await _armNativeWake();
        return;
      }
      _localWhisperRunning = true;
      _listening = true;
      _localSpeechStarted = false;
      _localSilenceMs = 0;
      _localSpeechMs = 0;
      if (mounted) setState(() => _status = 'Слушаю локально…');

      final pcm = await _localRecorder.startStream(const RecordConfig(
        encoder: AudioEncoder.pcm16bits,
        sampleRate: 16000,
        numChannels: 1,
        autoGain: true,
        echoCancel: true,
        noiseSuppress: true,
      ));

      final session = await _whisper.transcribeLive(
        model: WhisperModel.tiny,
        pcm16Stream: pcm,
        lang: 'ru',
        suppressNonSpeechTokens: true,
        keepModelLoaded: true,
        gateRmsMin: 0.0015,
        gateVoiceRatio: 2.5,
        gateNoiseFloorCap: 0.01,
      );
      _whisperSession = session;

      await _partialSub?.cancel();
      _partialSub = session.partials.listen((text) {
        _streamText = text.trim();
        if (mounted && _streamText.isNotEmpty) setState(() => _status = 'Распознаю: $_streamText');
      });

      _pcmSub = pcm.listen((bytes) {
        if (!_localWhisperRunning || bytes.isEmpty) return;
        var sum = 0.0;
        final sampleCount = bytes.length ~/ 2;
        for (var i = 0; i + 1 < bytes.length; i += 2) {
          final lo = bytes[i];
          final hi = bytes[i + 1];
          var sample = (lo | (hi << 8));
          if (sample >= 32768) sample -= 65536;
          sum += sample * sample;
        }
        final rms = sampleCount == 0 ? 0.0 : math.sqrt(sum / sampleCount) / 32768.0;
        final chunkMs = sampleCount <= 0 ? 0 : ((sampleCount * 1000) / 16000).round();
        if (rms > 0.012) {
          _localSpeechStarted = true;
          _localSilenceMs = 0;
          _localSpeechMs += chunkMs;
        } else if (_localSpeechStarted) {
          _localSilenceMs += chunkMs;
          if (_localSpeechMs >= 250 && _localSilenceMs >= 900) {
            _finishLocalWhisper();
          }
        }
        if (_localSpeechMs >= 12000) _finishLocalWhisper();
      }, onError: (_) => _finishLocalWhisper());
    } catch (e) {
      _localWhisperRunning = false;
      _listening = false;
      try { await _localRecorder.cancel(); } catch (_) {}
      try { await _whisperSession?.stop(); } catch (_) {}
      _whisperSession = null;
      if (mounted) setState(() => _status = 'Локальный STT: $e');
      await _armNativeWake();
    }
  }

  Future<void> _finishLocalWhisper() async {
    if (!_localWhisperRunning) return;
    _localWhisperRunning = false;
    _listening = false;
    try { await _pcmSub?.cancel(); } catch (_) {}
    _pcmSub = null;
    try { await _localRecorder.stop(); } catch (_) {}
    String phrase = '';
    try { phrase = (await _whisperSession?.stop() ?? '').trim(); } catch (_) {}
    _whisperSession = null;
    await _partialSub?.cancel();
    _partialSub = null;
    _streamText = '';
    if (phrase.isEmpty) {
      await _armNativeWake();
      return;
    }
    _awaitingCommand = false;
    if (mounted) setState(() => _status = 'Команда: $phrase');
    await _send(phrase, fromVoice: true);
  }

  Future<void> _stopNativeListening() async {
    if (!_android) return;
    try { await _pcmSub?.cancel(); } catch (_) {}
    _pcmSub = null;
    if (_localWhisperRunning) {
      _localWhisperRunning = false;
      try { await _localRecorder.stop(); } catch (_) {}
      try { await _whisperSession?.stop(); } catch (_) {}
      _whisperSession = null;
    }
    try { await _voice.invokeMethod('stop'); } catch (_) {}
    _listening = false;
  }

  Future<void> _onNativeVoiceEvent(dynamic event) async {
    if (!_android || !_voiceEnabled || !mounted) return;
    final value = event?.toString().trim() ?? '';
    if (value.isEmpty) return;
    if (value == '__READY__') { _voiceReady = true; _listening = false; setState(() => _status = 'Голосовой режим: двойной хлопок'); await _armNativeWake(); return; }
    if (value == '__TTS_READY__') { if (mounted) setState(() => _status = 'Голос готов · слушаю'); return; }
    if (value == '__TTS_ERROR__') { if (mounted) setState(() => _status = 'TTS недоступен: проверьте голосовой движок Android'); return; }
    if (value == '__WAKE__') { _listening = false; if (mounted) setState(() => _status = 'Пробуждение… слушаю'); await _startLocalWhisper(); return; }
    if (value == '__LISTENING__') { _listening = true; if (mounted) setState(() => _status = 'Слушаю…'); return; }
    if (value.startsWith('__ERROR__:')) {
      _listening = false;
      if (mounted) setState(() => _status = 'Ошибка голоса: ${value.substring(10)}');
      if (_voiceEnabled && !_busy) Future<void>.delayed(const Duration(milliseconds: 700), () { if (mounted) _armNativeWake(); });
      return;
    }
    if (value == '__END__') {
      _listening = false;
      if (_voiceEnabled && !_busy) Future<void>.delayed(const Duration(milliseconds: 450), () { if (mounted) _armNativeWake(); });
      return;
    }
    _listening = false;
    await _stopNativeListening();
    final phrase = value.trim();
    final command = phrase;
    _awaitingCommand = false;
    if (command.isEmpty) { Future<void>.delayed(const Duration(milliseconds: 300), () { if (mounted) _armNativeWake(); }); return; }
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
    if (endpoint.isEmpty) { if (mounted) setState(() => _status = 'Укажите endpoint AI в настройках'); return; }
    try {
      final old = _client; _client = null; await old?.dispose();
      _client = await JarvisIpc.connectAi(endpoint, apiKey: _apiKey.text.trim(), model: _model.text.trim());
      await _finishConnect();
    } catch (e) { if (mounted) setState(() => _status = 'Ошибка подключения AI: $e'); }
  }

  Future<void> _finishConnect() async {
    final client = _client; if (client == null) return;
    final tools = await client.listTools();
    await _partialSub?.cancel();
    _partialSub = client.partials().listen((text) { if (mounted) setState(() => _streamText = text); });
    if (mounted) setState(() => _status = _android ? 'AI подключён · ожидаю «Буся»' : 'Агент подключён · инструментов: ${tools.length}');
    if (_android && _voiceReady && _voiceEnabled) _startNativeListening();
  }

  Future<void> _settings() async {
    if (!_android) return;
    _voiceEnabled = false; _awaitingCommand = false; await _stopNativeListening();
    await showDialog<void>(context: context, builder: (ctx) => AlertDialog(
      title: const Text('AI-провайдер'),
      content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(controller: _endpoint, keyboardType: TextInputType.url, decoration: const InputDecoration(labelText: 'OpenAI-compatible endpoint')),
        TextField(controller: _model, decoration: const InputDecoration(labelText: 'Модель')),
        TextField(controller: _apiKey, obscureText: true, decoration: const InputDecoration(labelText: 'AI API key')),
        TextField(controller: _apiHostKey, obscureText: true, decoration: const InputDecoration(labelText: 'APIHOST key для голоса Леда')),
        const SizedBox(height: 12), const Text('Голос работает постоянно: произнесите команду — БУСЯ распознает её и ответит голосом. Голос и распознавание используют системные Android-службы.', style: TextStyle(fontSize: 12)),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(child: OutlinedButton.icon(onPressed: () => _voice.invokeMethod('open_tts_settings'), icon: const Icon(Icons.record_voice_over), label: const Text('Настройки голоса'))),
          const SizedBox(width: 8),
          Expanded(child: OutlinedButton.icon(onPressed: () => _voice.invokeMethod('install_tts_data'), icon: const Icon(Icons.download), label: const Text('Установить голос'))),
        ]),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Отмена')), FilledButton(onPressed: () { Navigator.pop(ctx); _connectAndroid(); }, child: const Text('Подключить'))],
    ));
    if (mounted && _voiceReady) { _voiceEnabled = true; setState(() => _status = 'Голосовой режим: двойной хлопок'); _armNativeWake(); }
  }

  Future<void> _toggleVoice() async {
    if (!_android) return;
    if (!_voiceReady) { await _initNativeVoice(); return; }
    _voiceEnabled = !_voiceEnabled; _awaitingCommand = false; await _saveSettings();
    if (!_voiceEnabled) { await _stopNativeListening(); if (mounted) setState(() => _status = 'Голос выключен'); return; }
    if (mounted) setState(() => _status = 'Голосовой режим: слушаю'); await _startNativeListening();
  }

  Future<void> _send(String text, {bool fromVoice = false}) async {
    final clean = text.trim(); final client = _client; final attachment = _attachment;
    if (clean.isEmpty || _busy) return;
    if (client == null) { if (mounted) setState(() => _status = 'Сначала подключите AI в настройках'); if (fromVoice) await _speak('Сначала подключите AI в настройках'); return; }
    setState(() { _busy = true; _streamText = ''; _messages.add(_Msg(attachment == null ? clean : '$clean\n📎 ${attachment.name}', isUser: true)); }); _scrollToBottom();
    try {
      final reply = await client.sendMessage(clean, attachment: attachment == null ? null : {'name': attachment.name, 'mime': attachment.mime, 'data': attachment.data});
      if (!mounted) return;
      setState(() { _messages.add(_Msg(reply.text, isUser: false)); _status = reply.needsConfirmation ? 'Требуется подтверждение' : (_android ? 'Голосовой режим: отвечаю голосом' : 'Готов'); });
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
    _voiceSub?.cancel(); _partialSub?.cancel(); _pcmSub?.cancel(); _localRecorder.dispose();
    if (_android) { _voice.invokeMethod('stop'); _voice.invokeMethod('dispose'); }
    _client?.dispose(); _input.dispose(); _endpoint.dispose(); _apiKey.dispose(); _model.dispose(); _apiHostKey.dispose(); _scroll.dispose(); super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('БУСЯ'), actions: [
      if (_android) IconButton(icon: Icon(_voiceEnabled ? Icons.mic : Icons.mic_off), tooltip: 'Голос', onPressed: _toggleVoice),
      if (_android) IconButton(icon: const Icon(Icons.settings), tooltip: 'AI', onPressed: _settings),
    ]),
    body: Column(children: [
      Expanded(child: ListView.builder(controller: _scroll, padding: const EdgeInsets.all(16), itemCount: _messages.length, itemBuilder: (_, i) { final m = _messages[i]; return Align(alignment: m.isUser ? Alignment.centerRight : Alignment.centerLeft, child: Container(margin: const EdgeInsets.only(bottom: 10), padding: const EdgeInsets.all(12), decoration: BoxDecoration(color: m.isUser ? kPanel : const Color(0xFF111D2B), borderRadius: BorderRadius.circular(14)), child: Text(m.text))); })),
      if (_streamText.isNotEmpty) Padding(padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6), child: Text(_streamText)),
      if (_attachment != null) Padding(padding: const EdgeInsets.fromLTRB(12, 4, 12, 0), child: Row(children: [Expanded(child: Text('📎 ${_attachment!.name}', maxLines: 1, overflow: TextOverflow.ellipsis)), IconButton(icon: const Icon(Icons.close), onPressed: () => setState(() => _attachment = null))])),
      Padding(padding: const EdgeInsets.fromLTRB(12, 4, 12, 12), child: Row(children: [
        IconButton(tooltip: 'Прикрепить файл', onPressed: _busy ? null : _pickFile, icon: const Icon(Icons.attach_file)),
        Expanded(child: TextField(controller: _input, textInputAction: TextInputAction.send, onSubmitted: _send, decoration: const InputDecoration(hintText: 'Команда БУСЕ', border: OutlineInputBorder()))),
        const SizedBox(width: 8), IconButton.filled(onPressed: _busy ? null : () { final text = _input.text; _input.clear(); _send(text); }, icon: const Icon(Icons.send)),
      ])),
      Padding(padding: const EdgeInsets.only(bottom: 10), child: Text(_status, style: const TextStyle(fontSize: 12))),
    ]),
  );
}
