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
  late final WebViewController _controller;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(
        onPageStarted: (_) {
          if (mounted) setState(() { _loading = true; _error = null; });
        },
        onPageFinished: (_) async {
          if (!mounted) return;
          setState(() => _loading = false);
          if (widget.initialPrompt.isNotEmpty) {
            await Clipboard.setData(ClipboardData(text: widget.initialPrompt));
          }
        },
        onWebResourceError: (error) {
          if (mounted && error.isForMainFrame == true) {
            setState(() { _loading = false; _error = error.description; });
          }
        },
      ))
      ..loadRequest(Uri.parse('https://gemini.google.com/app'));
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
          tooltip: 'Скопировать запрос',
          icon: const Icon(Icons.content_copy_rounded),
          onPressed: widget.initialPrompt.isEmpty ? null : () async {
            await Clipboard.setData(ClipboardData(text: widget.initialPrompt));
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Запрос скопирован. Вставьте его в поле Gemini.')),
              );
            }
          },
        ),
        IconButton(
          tooltip: 'Обновить',
          icon: const Icon(Icons.refresh_rounded),
          onPressed: () => _controller.reload(),
        ),
      ],
    ),
    body: Stack(children: [
      WebViewWidget(controller: _controller),
      if (_loading) const LinearProgressIndicator(),
      if (_error != null)
        Center(child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.cloud_off_rounded, size: 40),
            const SizedBox(height: 12),
            Text('Не удалось загрузить Gemini: $_error', textAlign: TextAlign.center),
            const SizedBox(height: 12),
            FilledButton(onPressed: () => _controller.reload(), child: const Text('Повторить')),
          ]),
        )),
    ]),
  );
}
