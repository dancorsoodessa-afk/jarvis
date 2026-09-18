import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'jarvis_client.dart';
import 'jarvis_reactor.dart';

void main() => runApp(const JarvisApp());
const kCyan = Color(0xFF37D5EE);
const kBg = Color(0xFF05080F);
const kPanel = Color(0xFF0D1622);

class JarvisApp extends StatelessWidget {
  const JarvisApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'БУСЯ',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          brightness: Brightness.dark,
          scaffoldBackgroundColor: kBg,
          colorScheme: ColorScheme.fromSeed(seedColor: kCyan, brightness: Brightness.dark, surface: kPanel),
          useMaterial3: true,
        ),
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
  static const _voice = MethodChannel('busya.voice');
  static const _voiceEvents = EventChannel('busya.voice.events');
  JarvisIpc? _jarvis;
  final _input = TextEditingController();
  final _scroll = ScrollController();
  final List<_Msg> _messages = [];
  bool _busy = false;
  bool _voiceReady = false;
  bool _listening = false;
  bool _speaking = false;
  String _status = 'Подключение к агенту…';
  String _toolStatus = '';
  String _streamText = '';
  StreamSubscription<String>? _partialSub;
  StreamSubscription<dynamic>? _voiceSub;

  @override
  void initState() {
    super.initState();
    _connect();
    if (Platform.isAndroid) _initVoice();
  }

  void _listenPartials() {
    _partialSub?.cancel();
    _partialSub = _jarvis!.partials().listen((text) {
      if (!mounted) return;
      setState(() => _streamText = text);
      if (_scroll.hasClients) _scroll.jumpTo(_scroll.position.maxScrollExtent);
    });
  }

  Future<void> _connect() async {
    final exeDir = File(Platform.resolvedExecutable).parent.path;
    final bundled = '${exeDir${{Platform.pathSeparator}jarvis.exe';
    try {
      _jarvis = await (File(bundled).existsSync()
          ? JarvisIpc.spawn(bundled)
          : JarvisIpc.spawn('python', ['-m', 'agent', '--ipc']));
      final tools = await _jarvis!.listTools();
      if (mounted) setState(() => _status = 'Агент готов · инструментов: ${{tools.length}');
      _listenPartials();
    } catch (e) {
      if (mounted) setState(() => _status = 'Агент не запущен: $e');
    }
  }

  Future<void> _initVoice() async {
    try {
      _voiceSub = _voiceEvents.receiveBroadcastStream().listen(_onVoiceEvent);
      final ok = await _voice.invokeMethod<bool>('initialize') ?? false;
      if (mounted) setState(() => _voiceReady = ok);
    } on MissingPluginException {
      if (mounted) setState(() => _voiceReady = false);
    } catch (e) {
      if (mounted) setState(() => _status = 'Голос недоступен: $e');
    }
  }

  void _onVoiceEvent(dynamic event) {
    if (!mounted) return;
    final text = event?.toString() ?? '';
    if (text == '__READY__') { setState(() => _voiceReady = true); return; }
    if (text == '__LISTENING__') { setState(() => _listening = true); return; }
    if (text == '__END__') { setState(() => _listening = false); return; }
    if (text == '__TTS_READY__') return;
    if (text.startsWith('__ERROR__:')) {
      setState(() {
        _listening = false;
        _speaking = false;
        _status = 'Голос: ${{text.substring('__ERROR__:'.length)}';
      });
      return;
    }
    if (text == '__TTS_ERROR__' || text.startsWith('__TTS_ERROR__')) {
      setState(() => _speaking = false);
      return;
    }
    if (text.isEmpty || text.startsWith('__')) return;

    setState(() => _listening = false);
    final phrase = text.trim();
    final lower = phrase.toLowerCase();
    if (lower == 'буся' || lower == 'буся.') {
      _say('Слушаю.');
      return;
    }
    if (lower.startsWith('буся ')) _send(phrase.substring(5).trim());
  }

  Future<void> _startVoice() async {
    if (!Platform.isAndroid || !_voiceReady || _busy) return;
    try {
      await _voice.invokeMethod('start');
    } catch (e) {
      if (mounted) setState(() => _status = 'Не удалось включить микрофон: $e');
    }
  }

  Future<void> _say(String text) async {
    if (!Platform.isAndroid || text.trim().isEmpty) return;
    if (mounted) setState(() => _speaking = true);
    try {
      await _voice.invokeMethod('speak', {'text': text});
    } catch (_) {
      if (mounted) setState(() => _speaking = false);
    }
  }

  Future<void> _send(String text, {Map<String, dynamic>? attachment}) async {
    text = text.trim();
    if ((text.isEmpty && attachment == null) || _jarvis == null || _busy) return;
    _input.clear();
    setState(() {
      _messages.add(_Msg(
        attachment == null ? text : '${{text.isEmpty ? 'Файл' : text}\n📎 ${{attachment['name']}',
        isUser: true,
      ));
      _busy = true;
      _streamText = '';
      _toolStatus = '';
      _listening = false;
    });
    try {
      var reply = await _jarvis!.sendMessage(text, attachment: attachment);
      if (reply.needsConfirmation && mounted) {
        final ok = await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('Подтверждение'),
            content: Text(reply.text),
            actions: [
              TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Отмена')),
              FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Выполнить')),
            ],
          ),
        );
        reply = await _jarvis!.sendMessage(ok == true ? 'да' : 'нет');
      }
      if (mounted) {
        setState(() {
          _messages.add(_Msg(reply.text, isUser: false));
          if (reply.toolUsed != null) _toolStatus = reply.toolUsed!;
        });
      }
      await _say(reply.text);
    } catch (e) {
      if (mounted) {
        setState(() => _messages.add(_Msg('Ошибка: $e', isUser: false)));
        await _say('Произошла ошибка.');
      }
    } finally {
      if (mounted) setState(() { _busy = false; _streamText = ''; _toolStatus = ''; });
    }
  }

  Future<void> _pickFile() async {
    if (!Platform.isAndroid || _busy || _jarvis == null) return;
    try {
      final attachment = await _voice.invokeMethod<Map<dynamic, dynamic>>('pick_file');
      if (attachment == null) return;
      final normalized = <String, dynamic>{
        'name': attachment['name'],
        'mime': attachment['mime'],
        'size': attachment['size'],
        'data': attachment['data'],
      };
      await _send('', attachment: normalized);
    } catch (e) {
      if (mounted) setState(() => _messages.add(_Msg('Ошибка файла: $e', isUser: false)));
    }
  }

  Future<void> _clearMemory() async {
    try {
      await _jarvis!.clearMemory();
      if (mounted) setState(() => _messages.add(_Msg('🧹 История диалога очищена.', isUser: false)));
    } catch (e) {
      if (mounted) setState(() => _messages.add(_Msg('Ошибка: $e', isUser: false)));
    }
  }

  @override
  void dispose() {
    _partialSub?.cancel();
    _voiceSub?.cancel();
    _jarvis?.dispose();
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: Column(
          children: [
            const SizedBox(height: 24),
            const SizedBox(width: 160, height: 160, child: JarvisReactor(color: kCyan)),
            const SizedBox(height: 8),
            Text(
              _speaking ? 'БУСЯ говорит' : (_listening ? 'БУСЯ слушает' : _status),
              style: const TextStyle(color: kCyan, fontSize: 12),
              textAlign: TextAlign.center,
            ),
            if (_toolStatus.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('🔧 $_toolStatus', style: TextStyle(color: kCyan.withOpacity(0.7), fontSize: 11)),
              ),
            const SizedBox(height: 8),
            Expanded(
              child: ListView.builder(
                controller: _scroll,
                padding: const EdgeInsets.all(16),
                itemCount: _messages.length,
                itemBuilder: (_, i) => _bubble(_messages[i]),
              ),
            ),
            if (_busy)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: _streamText.isNotEmpty
                    ? Align(alignment: Alignment.centerLeft, child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16),
                        child: Text('$_streamText▌')))
                    : const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: kCyan)),
              ),
            Padding(
              padding: const EdgeInsets.fromLTRB(8, 4, 8, 16),
              child: Row(
                children: [
                  if (Platform.isAndroid)
                    IconButton(
                      tooltip: 'Прикрепить файл',
                      onPressed: _busy ? null : _pickFile,
                      icon: const Icon(Icons.attach_file, color: Colors.white70),
                    ),
                  if (Platform.isAndroid)
                    IconButton(
                      tooltip: _listening ? 'Слушаю' : 'Голос',
                      onPressed: _busy ? null : _startVoice,
                      icon: Icon(_listening ? Icons.mic : Icons.mic_none, color: kCyan),
                    ),
                  Expanded(
                    child: TextField(
                      controller: _input,
                      onSubmitted: _send,
                      decoration: InputDecoration(
                        hintText: 'Сообщение или /команда…',
                        filled: true,
                        fillColor: kPanel,
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
                      ),
                    ),
                  ),
                  IconButton(
                    tooltip: 'Очистить память диалога',
                    onPressed: _busy ? null : _clearMemory,
                    icon: const Icon(Icons.delete_outline, color: Colors.white38),
                  ),
                  IconButton(
                    onPressed: _busy ? null : () => _send(_input.text),
                    icon: const Icon(Icons.send, color: kCyan),
                  ),
                ],
              ),
            ),
          ],
        ),
      );

  Widget _bubble(_Msg m) => Align(
        alignment: m.isUser ? Alignment.centerRight : Alignment.centerLeft,
        child: Container(
          margin: const EdgeInsets.symmetric(vertical: 4),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          constraints: const BoxConstraints(maxWidth: 520),
          decoration: BoxDecoration(
            color: m.isUser ? kCyan.withOpacity(0.15) : kPanel,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: m.isUser ? kCyan.withOpacity(0.4) : Colors.white10),
          ),
          child: SelectableText(m.text),
        ),
      );
}
