import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jarvis_ui/jarvis_reactor.dart';

void main() {
  testWidgets('reactor renders every state and handles live voice activity',
      (tester) async {
    const states = <JarvisVisualState>[
      JarvisVisualState.idle,
      JarvisVisualState.listening,
      JarvisVisualState.thinking,
      JarvisVisualState.speaking,
      JarvisVisualState.confirmation,
      JarvisVisualState.error,
      JarvisVisualState.exiting,
    ];

    for (final state in states) {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Center(
              child: SizedBox(
                width: 320,
                height: 320,
                child: JarvisReactor(state: state, activity: 0.85),
              ),
            ),
          ),
        ),
      );
      await tester.pump(const Duration(milliseconds: 40));
      expect(find.byType(JarvisReactor), findsOneWidget);
      expect(tester.takeException(), isNull, reason: 'state: $state');
    }
  });
}
