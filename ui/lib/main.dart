import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

import 'jarvis_client.dart';

const kCyan = Color(0xFF37D5EE);
const kBg = Color(0xFF05080F);
const kPanel = Color(0xFF0D1622);
const _wakeWord = 'буся';

void main() => runApp(const BusyaApp());

class BusyaApp extends StatelessWidget {
  const BusyaApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'БУСЯ',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          brightness: Brightness.dark,
          scaffoldBackgroundColor: kBg,
          colorScheme: ColorScheme.fromSeed(
            seedColor: kCyan,
            brightness: Brightness.dark,
          ),
          useMaterial3: true,
        ),
        home: const BusyaHomePage(),
      );
}

class _Msg {
  _Msg(this.text, {required this.isUser});
  final String text;
  final bool isUser;
}

class BusyaHomePage extends StatefulWidget {
  const BusyaHomePage({super.key});

  @override
  State<BusyaHomePage> createState() => _BusyaHomePageState();
}

class _BusyaHomePageState extends State<BusyaHomePage> {
  JarvisIpc? _client;
  final _input = TextEditingController();
  final _endpoint = TextEditingController();
  final _apiKey = TextEditingController();
  final _model = TextEditingController();
  final _scroll = ScrollController();
  final _messages = <_Msg>[];

  stt.SpeechToText? _speech;
  FlutterTts? _tts;
  StreamSubscription<String>? _partialSub;
  Timer? _restartTimer;
  Timer? _initRetryTimer;

  bool _voiceReady = false;
  bool _listening = false;
  bool _voiceEnabled = true;
  bool _awaitingCommand = false;
  bool _busy = false;
  bool _initializingVoice = false;

  String _status = 'БУСЯ запускается…';
  String _streamText = '';

  bool get _android => Platform.isAndroid;

  @override
  void initState() {
    super.initState();
    if (_android) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        Future<void>.delayed(const Duration(milliseconds: 1200), () {
          if (mounted) _initVoice();
        });
      });
    } else {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _connectDesktop();
      });
    }
  }

  Future<void> _initVoice() async {
    if (!_android || !mounted || _initializingVoice || _voiceReady) return;
    _initializingVoice = true;

    try {
      final speech = stt.SpeechToText();
      _speech = speech;
      final available = await speech.initialize(
        onStatus: (status) {
          if (!_android || !_voiceEnabled || !mounted) return;
          if (status == 'done' || status == 'notListening') {
            _listening = false;
            _scheduleRestart();
          }
        },
        onError: (_) {
          _listening = false;
          _scheduleRestart(const Duration(seconds: 1));
        },
      );

      if (!mounted) return;

      if (!available) {
        _voiceReady = false;
        _status = 'Микрофон/распознавание речи недоступно';
        setState(() {});
        _scheduleInitRetry();
        return;
      }

      _voiceReady = true;
      _voiceEnabled = true;
      setState(() => _status = 'Ожидаю слово «Буся»');
      await _startListening();
    } catch (e) {
      _voiceReady = false;
      if (mounted) setState(() => _status = 'Ошибка голоса: $e');
      _scheduleInitRetry();
    } finally {
      _initializingVoice = false;
    }
  }

  void _scheduleInitRetry() {
    if (!_android || !mounted || _voiceReady) return;
    _initRetryTimer?.cancel();
    _initRetryTimer = Timer(const Duration(seconds: 8), () {
      if (mounted) _initVoice();
    });
  }

  void _scheduleRestart([
    Duration delay = const Duration(milliseconds: 500),
  ]) {
    if (!_android || !_voiceReady || !_voiceEnabled || _busy || !mounted) {
      return;
    }
    _restartTimer?.cancel();
    _restartTimer = Timer(delay, _startListening);
  }

  Future<void> _startListening() async {
    final speech = _speech;
    if (!_android ||
        speech == null ||
        !_voiceReady ||
        !_voiceEnabled ||
        _listening ||
        _busy ||
        !mounted) {
      return;
    }

    try {
      _listening = true;
      await speech.listen(
        onResult: _onSpeechResult,
        listenFor: const Duration(seconds: 20),
        pauseFor: const Duration(seconds: 3),
        partialResults: true,
        listenMode: stt.ListenMode.confirmation,
      );
    } catch (_) {
      _listening = false;
      _scheduleRestart(const Duration(seconds: 1));
    }
  }

  String _commandAfterWakeWord(String phrase) {
    final lower = phrase.toLowerCase();
    final index = lower.indexOf(_wakeWord);
    if (index < 0) return '';
    return phrase.substring(index + _wakeWord.length).trim();
  }

  bool _containsWakeWord(String phrase) =>
      phrase.toLowerCase().contains(_wakeWord);

  Future<void> _onSpeechResult(SpeechRecognitionResult result) async {
    if (!result.finalResult || !_android || !_voiceEnabled || _busy) return;

    final phrase = result.recognizedWords.trim();
    if (phrase.isEmpty) return;

    if (!_awaitingCommand && !_containsWakeWord(phrase)) {
      return;
    }

    _restartTimer?.cancel();
    _listening = false;
    try {
      await _speech?.stop();
    } catch (_) {}

    final command = _awaitingCommand
        ? phrase
        : _commandAfterWakeWord(phrase);

    if (!_awaitingCommand && command.isEmpty) {
      _awaitingCommand = true;
      if (mounted) setState(() => _status = 'Слушаю команду…');
      await _speak('Слушаю');
      _scheduleRestart(const Duration(milliseconds: 700));
      return;
    }

    _awaitingCommand = false;
    if (command.isEmpty) {
      _scheduleRestart();
      return;
    }

    if (mounted) setState(() => _status = 'Команда: $command');
    await _send(command, fromVoice: true);
    _scheduleRestart(const Duration(milliseconds: 800));
  }

  Future<void> _speak(String text) async {
    if (!_android || !mounted || text.trim().isEmpty) return;
    try {
      final tts = _tts ??= FlutterTts();
      await tts.setLanguage('ru-RU');
      await tts.setSpeechRate(0.48);
      await tts.setVolume(1.0);
      await tts.setPitch(1.0);
      await tts.stop();
      await tts.speak(text.trim());
    } catch (_) {
      // Voice output must never terminate the application.
    }
  }

  Future<void> _connectDesktop() async {
    try {
      final dir = File(Platform.resolvedExecutable).parent.path;
      final exe = '$dir${Platform.pathSeparator}jarvis.exe';
      _client = await (File(exe).existsSync()
          ? JarvisIpc.spawn(exe)
          : JarvisIpc.spawn('python', ['-m', 'agent', '--ipc']));
      await _finishConnect();
    } catch (e) {
      if (mounted) setState(() => _status = 'Агент не запущен: $e');
    }
  }

  Future<void> _connectAndroid() async {
    final endpoint = _endpoint.text.trim();
    if (endpoint.isEmpty) {
      if (mounted) setState(() => _status = 'Укажите endpoint AI в настройках');
      return;
    }

    try {
      final old = _client;
      _client = null;
      await old?.dispose();
      _client = await JarvisIpc.connectAi(
        endpoint,
        apiKey: _apiKey.text.trim(),
        model: _model.text.trim(),
      );
      await _finishConnect();
    } catch (e) {
      if (mounted) setState(() => _status = 'Ошибка подключения AI: $e');
    }
  }

  Future<void> _finishConnect() async {
    final client = _client;
    if (client == null) return;
    final tools = await client.listTools();
    await _partialSub?.cancel();
    _partialSub = client.partials().listen((text) {
      if (mounted) setState(() => _streamText = text);
    });
    if (mounted) {
      setState(() => _status = _android
          ? 'AI подключён · ожидаю «Буся»'
          : 'Агент подключён · инструментов: ${tools.length}');
    }
    if (_android && _voiceReady && _voiceEnabled) {
      _scheduleRestart();
    }
  }

  Future<void> _settings() async {
    if (!_android) return;
    _voiceEnabled = false;
    _awaitingCommand = false;
    _restartTimer?.cancel();
    try {
      await _speech?.stop();
    } catch (_) {}
    _listening = false;

    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('AI-провайдер'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: _endpoint,
                keyboardType: TextInputType.url,
                decoration: const InputDecoration(
                  labelText: 'OpenAI-compatible endpoint',
                ),
              ),
              TextField(
                controller: _model,
                decoration: const InputDecoration(labelText: 'Модель'),
              ),
              TextField(
                controller: _apiKey,
                obscureText: true,
                decoration: const InputDecoration(labelText: 'API key'),
              ),
              const SizedBox(height: 12),
              const Text(
                'Активация голосом: только одно слово «Буся».',
                style: TextStyle(fontSize: 12),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () {
              Navigator.pop(ctx);
              _connectAndroid();
            },
            child: const Text('Подключить'),
          ),
        ],
      ),
    );

    if (mounted && _voiceReady) {
      _voiceEnabled = true;
      setState(() => _status = 'Ожидаю слово «Буся»');
      _scheduleRestart();
    }
  }

  Future<void> _toggleVoice() async {
    if (!_android) return;
    if (!_voiceReady) {
      await _initVoice();
      return;
    }

    _voiceEnabled = !_voiceEnabled;
    _awaitingCommand = false;
    _restartTimer?.cancel();

    if (!_voiceEnabled) {
      try {
        await _speech?.stop();
      } catch (_) {}
      _listening = false;
      if (mounted) setState(() => _status = 'Голос выключен');
      return;
    }

    if (mounted) setState(() => _status = 'Ожидаю слово «Буся»');
    await _startListening();
  }

  Future<void> _send(String text, {bool fromVoice = false}) async {
    final clean = text.trim();
    final client = _client;
    if (clean.isEmpty || _busy) return;

    if (client == null) {
      if (mounted) setState(() => _status = 'Сначала подключите AI в настройках');
      if (fromVoice) await _speak('Сначала подключите AI в настройках');
      return;
    }

    setState(() {
      _busy = true;
      _streamText = '';
      _messages.add(_Msg(clean, isUser: true));
    });
    _scrollToBottom();

    try {
      final reply = await client.sendMessage(clean);
      if (!mounted) return;
      setState(() {
        _messages.add(_Msg(reply.text, isUser: false));
        _status = reply.needsConfirmation
            ? 'Требуется подтверждение'
            : (_android ? 'Ожидаю слово «Буся»' : 'Готов');
      });
      _scrollToBottom();
      if (fromVoice) await _speak(reply.text);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _messages.add(_Msg('Ошибка: $e', isUser: false));
        _status = 'Ошибка';
      });
      if (fromVoice) await _speak('Произошла ошибка');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  void dispose() {
    _restartTimer?.cancel();
    _initRetryTimer?.cancel();
    _partialSub?.cancel();
    _speech?.stop();
    _tts?.stop();
    _client?.dispose();
    _input.dispose();
    _endpoint.dispose();
    _apiKey.dispose();
    _model.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: const Text('БУСЯ'),
          actions: [
            if (_android)
              IconButton(
                icon: Icon(_voiceEnabled ? Icons.mic : Icons.mic_off),
                tooltip: 'Голос',
                onPressed: _toggleVoice,
              ),
            if (_android)
              IconButton(
                icon: const Icon(Icons.settings),
                tooltip: 'AI',
                onPressed: _settings,
              ),
          ],
        ),
        body: Column(
          children: [
            Expanded(
              child: ListView.builder(
                controller: _scroll,
                padding: const EdgeInsets.all(16),
                itemCount: _messages.length,
                itemBuilder: (_, i) {
                  final m = _messages[i];
                  return Align(
                    alignment: m.isUser
                        ? Alignment.centerRight
                        : Alignment.centerLeft,
                    child: Container(
                      margin: const EdgeInsets.only(bottom: 10),
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: m.isUser ? kPanel : const Color(0xFF111D2B),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Text(m.text),
                    ),
                  );
                },
              ),
            ),
            if (_streamText.isNotEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                child: Text(_streamText),
              ),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _input,
                      textInputAction: TextInputAction.send,
                      onSubmitted: _send,
                      decoration: const InputDecoration(
                        hintText: 'Команда БУСЕ',
                        border: OutlineInputBorder(),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    onPressed: _busy
                        ? null
                        : () {
                            final text = _input.text;
                            _input.clear();
                            _send(text);
                          },
                    icon: const Icon(Icons.send),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Text(_status, style: const TextStyle(fontSize: 12)),
            ),
          ],
        ),
      );
}
