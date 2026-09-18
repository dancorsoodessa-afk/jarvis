import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'jarvis_client.dart';

const kCyan = Color(0xFF37D5EE);
const kBg = Color(0xFF05080F);
const kPanel = Color(0xFF0D1622);
const _wakeWord = 'буся';
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

class BusyaHomePage extends StatefulWidget {
  const BusyaHomePage({super.key});
  @override State<BusyaHomePage> createState() => _BusyaHomePageState();
}

class _BusyaHomePageState extends State<BusyaHomePage> {
  static const _voice = MethodChannel('busya.voice');
  static const _voiceEvents = EventChannel('busya.voice.events');
  JarvisIpc? _client;
  final _input = TextEditingController(), _endpoint = TextEditingController(text: _defaultAiEndpoint), _apiKey = TextEditingController(), _model = TextEditingController(text: _defaultAiModel);
  final _scroll = ScrollController();
  final _messages = <_Msg>[];
  StreamSubscription<dynamic>? _voiceSub;
  StreamSubscription<String>? _partialSub;
  bool _voiceReady = false, _listening = false, _voiceEnabled = true, _awaitingCommand = false, _busy = false;
  String _status = 'БУСЯ запускается…', _streamText = '';
  bool get _android => Platform.isAndroid;

  @override void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (_android) {
        await _loadSettings();
        await _initNativeVoice();
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
        final voiceEnabled = raw['voiceEnabled'];
        if (endpoint.isNotEmpty) _endpoint.text = endpoint;
        if (model.isNotEmpty) _model.text = model;
        _apiKey.text = apiKey;
        if (voiceEnabled is bool) _voiceEnabled = voiceEnabled;
      }
    } catch (_) {}
  }

  Future<void> _saveSettings() async {
    if (!_android) return;
    try {
      await _voice.invokeMethod('save_settings', {
        'endpoint': _endpoint.text.trim(),
        'model': _model.text.trim(),
        'apiKey': _apiKey.text.trim(),
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
      if (!available) { setState(() => _status = 'Распознавание речи недоступно'); return; }
      _voiceReady = true; _voiceEnabled = true;
      setState(() => _status = 'Ожидаю слово «Буся»');
      await _startNativeListening();
    } catch (e) { if (mounted) setState(() => _status = 'Ошибка голоса: $e'); }
  }

  Future<void> _startNativeListening() async {
    if (!_android || !_voiceReady || !_voiceEnabled || _busy || _listening) return;
    try { _listening = true; await _voice.invokeMethod('start'); }
    catch (e) { _listening = false; if (mounted) setState(() => _status = 'Ошибка микрофона: $e'); }
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
    if (value == '__READY__') { _voiceReady = true; _listening = false; setState(() => _status = 'Ожидаю слово «Буся»'); await _startNativeListening(); return; }
    if (value == '__TTS_READY__') return;
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
    final phrase = value.trim(), lower = phrase.toLowerCase(), index = lower.indexOf(_wakeWord);
    if (!_awaitingCommand && index < 0) {
      if (_voiceEnabled && !_busy) Future<void>.delayed(const Duration(milliseconds: 300), () { if (mounted) _startNativeListening(); });
      return;
    }
    final command = _awaitingCommand ? phrase : phrase.substring(index + _wakeWord.length).trim();
    if (!_awaitingCommand && command.isEmpty) {
      _awaitingCommand = true;
      if (mounted) setState(() => _status = 'Слушаю команду…');
      await _speak('Слушаю');
      Future<void>.delayed(const Duration(milliseconds: 250), () { if (mounted) _startNativeListening(); });
      return;
    }
    _awaitingCommand = false;
    if (command.isEmpty) { Future<void>.delayed(const Duration(milliseconds: 300), () { if (mounted) _startNativeListening(); }); return; }
    if (mounted) setState(() => _status = 'Команда: $command');
    await _send(command, fromVoice: true);
    if (_voiceEnabled && mounted) Future<void>.delayed(const Duration(milliseconds: 500), () { if (mounted) _startNativeListening(); });
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
        TextField(controller: _apiKey, obscureText: true, decoration: const InputDecoration(labelText: 'API key')),
        const SizedBox(height: 12), const Text('Бесплатный провайдер по умолчанию: OpenRouter. Активация голосом: только одно слово «Буся».', style: TextStyle(fontSize: 12)),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Отмена')), FilledButton(onPressed: () { Navigator.pop(ctx); _connectAndroid(); }, child: const Text('Подключить'))],
    ));
    if (mounted && _voiceReady) { _voiceEnabled = true; setState(() => _status = 'Ожидаю слово «Буся»'); _startNativeListening(); }
  }

  Future<void> _toggleVoice() async {
    if (!_android) return;
    if (!_voiceReady) { await _initNativeVoice(); return; }
    _voiceEnabled = !_voiceEnabled; _awaitingCommand = false; await _saveSettings();
    if (!_voiceEnabled) { await _stopNativeListening(); if (mounted) setState(() => _status = 'Голос выключен'); return; }
    if (mounted) setState(() => _status = 'Ожидаю слово «Буся»'); await _startNativeListening();
  }

  Future<void> _send(String text, {bool fromVoice = false}) async {
    final clean = text.trim(); final client = _client;
    if (clean.isEmpty || _busy) return;
    if (client == null) { if (mounted) setState(() => _status = 'Сначала подключите AI в настройках'); if (fromVoice) await _speak('Сначала подключите AI в настройках'); return; }
    setState(() { _busy = true; _streamText = ''; _messages.add(_Msg(clean, isUser: true)); }); _scrollToBottom();
    try {
      final reply = await client.sendMessage(clean);
      if (!mounted) return;
      setState(() { _messages.add(_Msg(reply.text, isUser: false)); _status = reply.needsConfirmation ? 'Требуется подтверждение' : (_android ? 'Ожидаю слово «Буся»' : 'Готов'); });
      _scrollToBottom();
      if (_android && fromVoice) await _speak(reply.text);
    } catch (e) {
      if (!mounted) return;
      setState(() { _messages.add(_Msg('Ошибка: $e', isUser: false)); _status = 'Ошибка'; });
      if (_android && fromVoice) await _speak('Произошла ошибка');
    } finally { if (mounted) setState(() => _busy = false); }
  }

  void _scrollToBottom() { WidgetsBinding.instance.addPostFrameCallback((_) { if (_scroll.hasClients) _scroll.animateTo(_scroll.position.maxScrollExtent, duration: const Duration(milliseconds: 180), curve: Curves.easeOut); }); }

  @override void dispose() {
    _voiceSub?.cancel(); _partialSub?.cancel();
    if (_android) { _voice.invokeMethod('stop'); _voice.invokeMethod('dispose'); }
    _client?.dispose(); _input.dispose(); _endpoint.dispose(); _apiKey.dispose(); _model.dispose(); _scroll.dispose(); super.dispose();
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
      Padding(padding: const EdgeInsets.fromLTRB(12, 4, 12, 12), child: Row(children: [
        Expanded(child: TextField(controller: _input, textInputAction: TextInputAction.send, onSubmitted: _send, decoration: const InputDecoration(hintText: 'Команда БУСЕ', border: OutlineInputBorder()))),
        const SizedBox(width: 8), IconButton.filled(onPressed: _busy ? null : () { final text = _input.text; _input.clear(); _send(text); }, icon: const Icon(Icons.send)),
      ])),
      Padding(padding: const EdgeInsets.only(bottom: 10), child: Text(_status, style: const TextStyle(fontSize: 12))),
    ]),
  );
}
