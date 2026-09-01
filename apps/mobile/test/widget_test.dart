import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:guiyin_mobile/core/api_client.dart';
import 'package:guiyin_mobile/core/session.dart';
import 'package:guiyin_mobile/features/privacy/elder_manage_screen.dart';
import 'package:guiyin_mobile/main.dart';

class _FakeApiClient extends ApiClient {
  _FakeApiClient() : super(baseUrl: 'http://127.0.0.1:8000/api/v1');

  final _smsRequest = Completer<Map<String, dynamic>>();

  @override
  Future<Map<String, dynamic>> requestSms(String phone) {
    return _smsRequest.future;
  }

  void completeSmsRequest() {
    _smsRequest.complete({'debug_code': '123456'});
  }

  @override
  Future<List<Map<String, dynamic>>> dataAccessHistory() async => [];
}

class _NoFamilySessionController extends SessionController {
  _NoFamilySessionController(super.api);

  @override
  Future<void> restore() async {
    state = const SessionState();
  }
}

void main() {
  test('app root can be constructed', () {
    expect(const GuiyinApp(), isA<GuiyinApp>());
  });

  testWidgets('requesting an SMS code keeps the login form state',
      (tester) async {
    FlutterSecureStorage.setMockInitialValues({});
    final api = _FakeApiClient();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          apiClientProvider.overrideWithValue(api),
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
    await tester.pump();

    // The request is deliberately still pending. The router must not replace
    // the login page with /loading or its text fields would be cleared.
    expect(find.byType(TextField), findsNWidgets(2));
    expect(find.text('13800138000'), findsOneWidget);
    expect(find.text('张叔叔'), findsOneWidget);

    api.completeSmsRequest();
    await tester.pumpAndSettle();

    expect(find.text('6位验证码'), findsOneWidget);
    expect(find.text('123456'), findsOneWidget);
    expect(find.text('登录'), findsOneWidget);
  });

  testWidgets('elder data page does not spin forever without family context',
      (tester) async {
    FlutterSecureStorage.setMockInitialValues({});
    final api = _FakeApiClient();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          apiClientProvider.overrideWithValue(api),
          sessionProvider.overrideWith(
            (ref) => _NoFamilySessionController(api),
          ),
        ],
        child: const MaterialApp(home: ElderManageScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(find.text('尚未读取到家庭信息，请返回首页后重试'), findsOneWidget);
  });
}
