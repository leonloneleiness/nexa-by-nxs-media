import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:nexa_mobile/main.dart';

import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));
  for (final status in [200, 401, 429, 500]) {
    testWidgets('Chat response HTTP $status', (tester) async {
      FlutterSecureStorage.setMockInitialValues({
        'nexa.endpoint': 'https://example.test/v1/chat/completions',
        'nexa.model': 'test-model',
        'nexa.token': 'test-token',
      });
      final client = MockClient((request) async {
        expect(request.headers['Authorization'], 'Bearer test-token');
        expect(jsonDecode(request.body)['model'], 'test-model');
        return http.Response(
          jsonEncode({
            'choices': [
              {
                'message': {'content': 'Test answer'},
              },
            ],
          }),
          status,
        );
      });
      await tester.pumpWidget(NexaApp(client: client));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), 'Hello');
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pumpAndSettle();
      if (status == 200) {
        expect(find.text('Test answer'), findsOneWidget);
      } else {
        expect(find.textContaining('Yêu cầu thất bại'), findsOneWidget);
        expect(find.text('Test answer'), findsNothing);
        expect(find.text('Hello'), findsOneWidget);
      }
      client.close();
    });
  }
  testWidgets('NEXA starts with chat UI', (tester) async {
    await tester.pumpWidget(const NexaApp());
    await tester.pumpAndSettle();
    expect(find.text('NEXA'), findsOneWidget);
    expect(find.textContaining('Xin chào'), findsOneWidget);
    expect(find.byIcon(Icons.settings_outlined), findsOneWidget);
  });
  testWidgets('Rejects sending without secure endpoint and model', (
    tester,
  ) async {
    await tester.pumpWidget(const NexaApp());
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Xin chào');
    await tester.tap(find.byIcon(Icons.arrow_upward));
    await tester.pumpAndSettle();
    expect(find.textContaining('Cần endpoint HTTPS'), findsOneWidget);
    expect(find.text('Xin chào'), findsOneWidget);
  });
}
