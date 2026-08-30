import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'api_client.dart';

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient());

final sessionProvider = StateNotifierProvider<SessionController, SessionState>(
  (ref) => SessionController(ref.read(apiClientProvider)),
);

class SessionState {
  const SessionState({
    this.loading = false,
    this.token,
    this.userId,
    this.displayName,
    this.familyId,
    this.role,
    this.error,
  });

  final bool loading;
  final String? token;
  final String? userId;
  final String? displayName;
  final String? familyId;
  final String? role;
  final String? error;

  bool get isAuthenticated => token != null && userId != null;
  bool get hasFamily => familyId != null;
  bool get isElder => role == 'elder';

  SessionState copyWith({
    bool? loading,
    String? token,
    String? userId,
    String? displayName,
    String? familyId,
    String? role,
    String? error,
    bool clearError = false,
  }) {
    return SessionState(
      loading: loading ?? this.loading,
      token: token ?? this.token,
      userId: userId ?? this.userId,
      displayName: displayName ?? this.displayName,
      familyId: familyId ?? this.familyId,
      role: role ?? this.role,
      error: clearError ? null : error ?? this.error,
    );
  }
}

class SessionController extends StateNotifier<SessionState> {
  SessionController(this._api) : super(const SessionState(loading: true)) {
    restore();
  }

  static const _storage = FlutterSecureStorage();
  final ApiClient _api;

  Future<void> restore() async {
    final token = await _storage.read(key: 'access_token');
    if (token == null) {
      state = const SessionState();
      return;
    }
    _api.setToken(token);
    try {
      final me = await _api.me();
      state = SessionState(
        token: token,
        userId: me['id'] as String?,
        displayName: me['display_name'] as String?,
      );
      await refreshFamilyContext();
    } catch (_) {
      await logout();
    }
  }

  Future<String?> requestSms(String phone) async {
    state = state.copyWith(loading: true, clearError: true);
    try {
      final result = await _api.requestSms(phone);
      state = state.copyWith(loading: false);
      return result['debug_code'] as String?;
    } catch (error) {
      state = state.copyWith(loading: false, error: error.toString());
      return null;
    }
  }

  Future<bool> login({
    required String phone,
    required String code,
    required String displayName,
  }) async {
    state = state.copyWith(loading: true, clearError: true);
    try {
      final result = await _api.verifySms(
        phone: phone,
        code: code,
        displayName: displayName,
      );
      final token = result['access_token'] as String;
      _api.setToken(token);
      await _storage.write(key: 'access_token', value: token);
      final me = await _api.me();
      state = SessionState(
        token: token,
        userId: me['id'] as String,
        displayName: me['display_name'] as String,
      );
      await refreshFamilyContext();
      return true;
    } catch (error) {
      state = state.copyWith(loading: false, error: error.toString());
      return false;
    }
  }

  Future<void> refreshFamilyContext() async {
    final families = await _api.families();
    if (families.isEmpty) {
      state = state.copyWith(loading: false, clearError: true);
      return;
    }
    final familyId = families.first['id'] as String;
    final members = await _api.familyMembers(familyId);
    final mine = members.cast<Map<String, dynamic>?>().firstWhere(
          (member) => member?['user_id'] == state.userId,
          orElse: () => null,
        );
    state = state.copyWith(
      loading: false,
      familyId: familyId,
      role: mine?['role'] as String?,
      clearError: true,
    );
  }

  Future<void> logout() async {
    await _storage.delete(key: 'access_token');
    _api.setToken(null);
    state = const SessionState();
  }
}

