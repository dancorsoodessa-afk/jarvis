import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:jarvis_ui/jarvis_client.dart';

void main() {
  test('recovers from a stale OpenRouter model using the configured API model list', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    server.listen((request) async {
      request.response.headers.contentType = ContentType.json;
      if (request.uri.path == '/v1/models') {
        request.response.write(jsonEncode({
          'data': [
            {'id': 'gemini-3.6-flash'},
          ],
        }));
        await request.response.close();
        return;
      }

      if (request.uri.path == '/v1/chat/completions') {
        final payload = jsonDecode(await utf8.decoder.bind(request).join()) as Map<String, dynamic>;
        if (payload['model'] != 'gemini-3.6-flash') {
          request.response.statusCode = HttpStatus.notFound;
          request.response.write(jsonEncode({
            'error': {'message': 'model openrouter/free not found'},
          }));
        } else {
          request.response.write(jsonEncode({
            'choices': [
              {'message': {'content': 'OK'}},
            ],
          }));
        }
        await request.response.close();
        return;
      }

      request.response.statusCode = HttpStatus.notFound;
      await request.response.close();
    });

    final client = await JarvisIpc.connectAi(
      'http://127.0.0.1:${server.port}/v1',
      apiKey: 'test-key',
      model: 'openrouter/free',
    );

    try {
      await client.checkConnection();
      final reply = await client.sendMessage('Проверка подключения');
      expect(reply.text, 'OK');
    } finally {
      await client.dispose();
      await server.close(force: true);
    }
  });
}
