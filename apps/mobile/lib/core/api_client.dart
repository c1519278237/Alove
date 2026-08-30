import 'package:dio/dio.dart';

class ApiException implements Exception {
  ApiException(this.code, this.message);

  final String code;
  final String message;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({String? baseUrl})
      : _dio = Dio(
          BaseOptions(
            baseUrl: baseUrl ??
                const String.fromEnvironment(
                  'API_BASE_URL',
                  defaultValue: 'http://10.0.2.2:8000/api/v1',
                ),
            connectTimeout: const Duration(seconds: 10),
            receiveTimeout: const Duration(seconds: 40),
            headers: {'Content-Type': 'application/json'},
          ),
        ) {
    _dio.interceptors.add(
      InterceptorsWrapper(
        onError: (error, handler) {
          final body = error.response?.data;
          if (body is Map<String, dynamic> && body['error'] is Map) {
            final apiError = body['error'] as Map;
            handler.reject(
              DioException(
                requestOptions: error.requestOptions,
                response: error.response,
                error: ApiException(
                  apiError['code']?.toString() ?? 'UNKNOWN_ERROR',
                  apiError['message']?.toString() ?? '请求失败，请稍后重试',
                ),
              ),
            );
            return;
          }
          handler.next(error);
        },
      ),
    );
  }

  final Dio _dio;

  void setToken(String? token) {
    if (token == null) {
      _dio.options.headers.remove('Authorization');
    } else {
      _dio.options.headers['Authorization'] = 'Bearer $token';
    }
  }

  Future<Map<String, dynamic>> requestSms(String phone) async {
    return _post('/auth/sms/request', {'phone': phone});
  }

  Future<Map<String, dynamic>> verifySms({
    required String phone,
    required String code,
    required String displayName,
  }) async {
    return _post('/auth/sms/verify', {
      'phone': phone,
      'code': code,
      'display_name': displayName,
    });
  }

  Future<Map<String, dynamic>> me() => _get('/me');

  Future<List<Map<String, dynamic>>> families() => _getList('/families');

  Future<Map<String, dynamic>> createFamily({
    required String name,
    required String role,
  }) async {
    return _post('/families', {
      'name': name,
      'my_role': role,
    });
  }

  Future<Map<String, dynamic>> acceptInvite(String code) async {
    return _post('/family-invites/$code/accept', {'code': code});
  }

  Future<List<Map<String, dynamic>>> familyMembers(String familyId) {
    return _getList('/families/$familyId/members');
  }

  Future<Map<String, dynamic>> createInvite(
    String familyId, {
    required String role,
    required String relationshipLabel,
  }) {
    return _post('/families/$familyId/invites', {
      'role': role,
      'relationship_label': relationshipLabel,
      'expires_hours': 24,
    });
  }

  Future<Map<String, dynamic>> createConversation(String familyId) {
    return _post('/conversations', {
      'family_id': familyId,
      'sharing_level': 'private',
    });
  }

  Future<Map<String, dynamic>> sendMessage(
    String conversationId,
    String text,
  ) {
    return _post('/conversations/$conversationId/messages', {'text': text});
  }

  Future<Map<String, dynamic>> setConversationSharing(
    String conversationId,
    String level,
  ) {
    return _post('/conversations/$conversationId/sharing-level', {
      'sharing_level': level,
    });
  }

  Future<List<Map<String, dynamic>>> inbox() =>
      _getList('/family-messages/inbox');

  Future<List<Map<String, dynamic>>> reminders() => _getList('/reminders');

  Future<List<Map<String, dynamic>>> elderNeeds(String elderId) =>
      _getList('/elders/$elderId/needs');

  Future<List<Map<String, dynamic>>> elderReports(String elderId) =>
      _getList('/elders/$elderId/care-reports');

  Future<Map<String, dynamic>> generateReport(String elderId) =>
      _post('/elders/$elderId/care-reports/generate', {'period_days': 7});

  Future<Map<String, dynamic>> _get(String path) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>(path);
      return response.data ?? <String, dynamic>{};
    } on DioException catch (error) {
      throw error.error is ApiException
          ? error.error as ApiException
          : ApiException('NETWORK_ERROR', '网络连接失败，请检查后端服务');
    }
  }

  Future<List<Map<String, dynamic>>> _getList(String path) async {
    try {
      final response = await _dio.get<List<dynamic>>(path);
      return (response.data ?? const <dynamic>[])
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList();
    } on DioException catch (error) {
      throw error.error is ApiException
          ? error.error as ApiException
          : ApiException('NETWORK_ERROR', '网络连接失败，请检查后端服务');
    }
  }

  Future<Map<String, dynamic>> _post(
    String path,
    Map<String, dynamic> data,
  ) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(path, data: data);
      return response.data ?? <String, dynamic>{};
    } on DioException catch (error) {
      throw error.error is ApiException
          ? error.error as ApiException
          : ApiException('NETWORK_ERROR', '网络连接失败，请检查后端服务');
    }
  }
}
