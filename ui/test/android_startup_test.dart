import 'package:flutter_test/flutter_test.dart';
import 'package:jarvis_ui/main.dart';

void main() {
  testWidgets('JARVIS renders its first frame without native services', (tester) async {
    await tester.pumpWidget(const JarvisApp());
    await tester.pump();

    expect(find.byType(JarvisApp), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
