// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:easylend_kiosk/app.dart';

void main() {
  testWidgets('renders screen switcher in debug mode', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      const ProviderScope(child: App()),
    );
    await tester.pumpAndSettle();
    expect(find.text('Screen Switcher'), findsOneWidget);
    expect(find.text('Login Screen'), findsOneWidget);
  });
}
