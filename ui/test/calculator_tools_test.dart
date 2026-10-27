import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jarvis_ui/tools/calculator/calculator_screen.dart';

void main() {
  testWidgets('calculator evaluates parentheses and multiplication', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: JarvisCalculatorScreen()));
    await tester.enterText(find.byType(TextField), '12 * (3 + 4)');
    await tester.tap(find.text('Вычислить'));
    await tester.pump();
    expect(find.text('12 * (3 + 4) = 84'), findsOneWidget);
  });

  testWidgets('calculator reports division by zero', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: JarvisCalculatorScreen()));
    await tester.enterText(find.byType(TextField), '10 / 0');
    await tester.tap(find.text('Вычислить'));
    await tester.pump();
    expect(find.textContaining('Деление на ноль'), findsOneWidget);
  });
}
