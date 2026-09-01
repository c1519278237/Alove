import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:guiyin_mobile/core/api_client.dart';
import 'package:guiyin_mobile/core/session.dart';
import 'package:guiyin_mobile/main.dart';

class _FakeApiClient extends ApiClient {
  _FakeApiClient() : super(baseUrl: 'http://127.0.0.1:8000/api/v1');

  @override
  Future<Map<String, dynamic>> requestSms(String phone) async {
    await Future<void>.delayed(const Duration(milliseconds: 1));
    return {'debug_code': '123456'};
  }
}

void main() {
  test('app root can be constructed', () {
    expect(const GuiyinApp(), isA<GuiyinApp>());
  });

  testWidgets('requesting an SMS code keeps the login form state',
      (tester) async {
    FlutterSecureStorage.setMockInitialValues({});
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          apiClientProvider.overrideWithValue(_FakeApiClient()),
        ],
        child: const GuiyinApp(),
      ),
    );
    await tester.pumpAndSettle();

    final fields = find.byType(TextField);
    expect(fields, findsNWidgets(2));
    await tester.enterText(fields.at(0), '13800138000');
    await tester.enterText(fields.at(1), '张叔叔');
    await tester.tap(find.text('获取验证码'));
    await tester.pumpAndSettle();

    expect(find.text('6位验证码'), findsOneWidget);
    expect(find.text('123456'), findsOneWidget);
    expect(find.text('登录'), findsOneWidget);
  });
}
