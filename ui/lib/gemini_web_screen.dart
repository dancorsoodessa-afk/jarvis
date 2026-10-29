import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:webview_flutter/webview_flutter.dart';

class GeminiWebScreen extends StatefulWidget {
  const GeminiWebScreen({super.key, this.initialPrompt = ''});
  final String initialPrompt;

  @override
  State<GeminiWebScreen> createState() => _GeminiWebScreenState();
}

class _GeminiWebScreenState extends State<GeminiWebScreen> {
  static final Uri _geminiUri = Uri.parse('https://gemini.google.com/app');
  static final Uri _signInUri = Uri.parse('https://accounts.google.com/');
  late final WebViewController _controller;
  bool _loading = true;
  bool _showingSignIn = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(
        onPageStarted: (url) {
          if (!mounted) return;
          setState(() {
            _loading = true;
            _error = null;
            if (url.startsWith('https://gemini.google.com/')) {
              _showingSignIn = false;
            }
          });
        },
        onPageFinished: (url) async {
          if (!mounted) return;
          setState(() => _loading = false);
          if (url.startsWith('https://gemini.google.com/') &&
              widget.initialPrompt.isNotEmpty) {
            await Clipboard.setData(ClipboardData(text: widget.initialPrompt));
          }
        },
        onWebResourceError: (error) {
          if (mounted && error.isForMainFrame == true) {
            setState(() {
              _loading = false;
              _error = error.description;
            });
          }
        },
      ))
      ..loadRequest(_geminiUri);
  }

  Future<void> _openSignIn() async {
    setState(() {
      _showingSignIn = true;
      _loading = true;
      _error = null;
    });
    await _controller.loadRequest(_signInUri);
  }

  Future<void> _openGemini() async {
    setState(() {
      _showingSignIn = false;
      _loading = true;
      _error = null;
    });
    await _controller.loadRequest(_geminiUri);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      leading: IconButton(
        tooltip: 'Назад в JARVIS',
        icon: const Icon(Icons.arrow_back),
        onPressed: () => Navigator.of(context).pop(),
      ),
      title: const Row(children: [
        Icon(Icons.hub_rounded, color: Color(0xFF42E8FF)),
        SizedBox(width: 8),
        Text('JARVIS · Gemini'),
      ]),
      actions: [
        IconButton(
          tooltip: 'Войти в Google',
          icon: const Icon(Icons.login_rounded),
          onPressed: _openSignIn,
        ),
        IconButton(
          tooltip: 'Открыть Gemini',
          icon: const Icon(Icons.auto_awesome_rounded),
          onPressed: _openGemini,
        ),
        IconButton(
          tooltip: 'Обновить',
          icon: const Icon(Icons.refresh_rounded),
          onPressed: () => _controller.reload(),
        ),
      ],
    ),
    body: Column(children: [
      Material(
        color: const Color(0xFF0D1622),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
          child: Row(children: [
            Icon(
              _showingSignIn ? Icons.lock_open_rounded : Icons.info_outline_rounded,
              color: const Color(0xFF42E8FF),
              size: 20,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                _showingSignIn
                    ? 'Войдите в свой аккаунт Google, затем нажмите кнопку Gemini.'
                    : 'Для работы войдите в Google. Запрос скопирован в буфер обмена — при необходимости вставьте его в Gemini.',
                style: const TextStyle(fontSize: 12, height: 1.3),
              ),
            ),
            const SizedBox(width: 8),
            TextButton(
              onPressed: _showingSignIn ? _openGemini : _openSignIn,
              child: Text(_showingSignIn ? 'Gemini' : 'Войти'),
            ),
          ]),
        ),
      ),
      Expanded(
        child: Stack(children: [
          WebViewWidget(controller: _controller),
          if (_loading) const LinearProgressIndicator(),
          if (_error != null)
            Center(child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                const Icon(Icons.cloud_off_rounded, size: 40),
                const SizedBox(height: 12),
                Text('Не удалось загрузить страницу: $_error', textAlign: TextAlign.center),
                const SizedBox(height: 12),
                Wrap(
                  alignment: WrapAlignment.center,
                  spacing: 8,
                  children: [
                    FilledButton(onPressed: _openGemini, child: const Text('Повторить Gemini')),
                    OutlinedButton(onPressed: _openSignIn, child: const Text('Войти в Google')),
                  ],
                ),
              ]),
            )),
        ]),
      ),
    ]),
  );
}
