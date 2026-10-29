import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

class GeminiWebScreen extends StatefulWidget {
  const GeminiWebScreen({super.key, this.initialPrompt = ''});
  final String initialPrompt;

  @override
  State<GeminiWebScreen> createState() => _GeminiWebScreenState();
}

class _GeminiWebScreenState extends State<GeminiWebScreen> {
  static final Uri _geminiUri = Uri.parse('https://gemini.google.com/app');
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
          if (url.startsWith('https://gemini.google.com/')) {
            // Dismiss only visible, clearly labelled Gemini invitation controls.
            try {
              await _controller.runJavaScript(r'''
                (() => {
                  const dismiss = () => {
                    const visible = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
                    const labels = /^(close|dismiss|закрыть|no thanks|not now|maybe later|не сейчас|нет, спасибо|позже|пропустить)$/i;
                    const candidates = Array.from(document.querySelectorAll('[role="dialog"] button, [role="dialog"] [role="button"], button[aria-label], [role="button"][aria-label]'));
                    const target = candidates.find(e => {
                      if (!visible(e)) return false;
                      const label = (e.getAttribute('aria-label') || e.getAttribute('title') || e.innerText || '').trim();
                      return labels.test(label);
                    });
                    if (target) target.click();
                  };
                  dismiss();
                  setTimeout(dismiss, 700);
                  setTimeout(dismiss, 1800);
                })();
              ''');
            } catch (_) { /* Gemini may not expose a dismissible invitation. */ }
            if (widget.initialPrompt.isNotEmpty) {
              await Clipboard.setData(ClipboardData(text: widget.initialPrompt));
            }
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
    // Google blocks account sign-in inside embedded WebViews.
    try {
      final opened = await launchUrl(_geminiUri, mode: LaunchMode.externalApplication);
      if (!mounted) return;
      setState(() {
        _showingSignIn = true;
        _error = opened ? null : 'Не удалось открыть Gemini в браузере. Проверьте, установлен ли браузер.';
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = 'Не удалось открыть вход Google: $error');
    }
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
                    ? 'Вход Google открывается в системном браузере: Google блокирует авторизацию внутри WebView.'
                    : 'Запрос скопирован. Для входа нажмите «Войти» — откроется официальный Gemini в браузере.',
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
