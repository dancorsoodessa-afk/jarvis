import 'dart:io';
import 'package:flutter/material.dart';

class JarvisSystemScreen extends StatelessWidget {
  const JarvisSystemScreen({super.key});
  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    return Scaffold(
      appBar: AppBar(title: const Text('Система и диагностика')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        const Text('ДИАГНОСТИКА УСТРОЙСТВА', style: TextStyle(color: Color(0xFF37D5EE), letterSpacing: 1.5, fontWeight: FontWeight.bold)),
        const SizedBox(height: 12),
        _row('Платформа', Platform.operatingSystem),
        _row('Версия ОС', Platform.operatingSystemVersion),
        _row('Архитектура процесса', Platform.version.split(' ').first),
        _row('Время устройства', '${now.toLocal()}'),
        _row('Интернет', 'Проверяется отдельными сетевыми инструментами'),
        const SizedBox(height: 12),
        const Text('Этот экран показывает доступные приложению сведения. Он не утверждает, что имеет доступ к CPU, RAM, процессам или управлению другими приложениями Android.', style: TextStyle(color: Colors.white60)),
      ]),
    );
  }
  Widget _row(String label, String value) => Card(
    child: ListTile(title: Text(label), subtitle: SelectableText(value)),
  );
}
