import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:jarvis_ui/jarvis_client.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late HttpServer primary;
  late HttpServer fallback;
  late JarvisIpc client;
  var primaryCalls = 0;
  var fallbackCalls = 0;
  var primaryStatusCode = HttpStatus.unauthorized;

  setUp(() async {
    primaryCalls = 0;
    fallbackCalls = 0;
    primaryStatusCode = HttpStatus.unauthorized;

    primary = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    primary.listen((request) async {
      primaryCalls++;
      request.response.statusCode = primaryStatusCode;
      request.response.headers.contentType = ContentType.json;
      request.response.write(jsonEncode({
        'error': {'message': 'invalid primary key'},
      }));
      await request.response.close();
    });

    fallback = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    fallback.listen((request) async {
      fallbackCalls++;
      request.response.headers.contentType = ContentType.json;
      request.response.write(jsonEncode({
        'model': 'test-model',
        'choices': [
          {'message': {'content': 'backup answer $fallbackCalls'}},
        ],
      }));
      await request.response.close();
    });

    client = await JarvisIpc.connectAi(
      'http://127.0.0.1:${primary.port}/v1',
      apiKey: 'primary-key',
      model: 'test-model',
      fallbacks: [
        {
          'name': 'backup',
          'url': 'http://127.0.0.1:${fallback.port}/v1',
          'key': 'backup-key',
          'model': 'test-model',
        },
      ],
    );
  });

  tearDown(() async {
    await client.dispose();
    await primary.close(force: true);
    await fallback.close(force: true);
  });

  test('retries an auth failure on the configured fallback', () async {
    final reply = await client.sendMessage('first request');
    expect(reply.text, 'backup answer 1');
    expect(primaryCalls, 1);
    expect(fallbackCalls, 1);
  });

  test('fallback success does not replace primary for the next request', () async {
    await client.sendMessage('first request');
    final reply = await client.sendMessage('second request');

    expect(reply.text, 'backup answer 2');
    expect(primaryCalls, 2);
    expect(fallbackCalls, 2);
  });

  test('uses fallback when the primary endpoint or model returns 404', () async {
    primaryStatusCode = HttpStatus.notFound;
    final reply = await client.sendMessage('request with missing primary route');

    expect(reply.text, 'backup answer 1');
    expect(primaryCalls, 1);
    expect(fallbackCalls, 1);
  });
}
