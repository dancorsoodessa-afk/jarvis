import 'package:flutter_test/flutter_test.dart';
import 'package:jarvis_ui/ai_config.dart';

void main() {
  group('JARVIS AI defaults', () {
    test('uses the documented Hugging Face endpoint', () {
      expect(jarvisDefaultAiEndpoint, 'https://router.huggingface.co/v1');
      expect(jarvisDefaultAiEndpoint, isNot(contains('api.openai.com')));
      expect(jarvisDefaultAiEndpoint, isNot(contains('api.groq.com')));
    });

    test('defines usable, non-empty default model IDs', () {
      expect(jarvisDefaultModel1, isNotEmpty);
      expect(jarvisDefaultModel2, isNotEmpty);
      expect(jarvisDefaultModel3, isNotEmpty);
      expect({
        jarvisDefaultModel1,
        jarvisDefaultModel2,
        jarvisDefaultModel3,
      }.length, 3, reason: 'Primary and backup defaults should be distinct.');
    });
  });
}
