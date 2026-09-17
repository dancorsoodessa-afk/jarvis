import 'package:flutter_test/flutter_test.dart';
import 'package:jarvis_ui/jarvis_reactor.dart';

void main() {
  testWidgets('JARVIS reactor renders', (tester) async {
    await tester.pumpWidget(const JarvisReactor());
    expect(find.byType(JarvisReactor), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 50));
  });
}
