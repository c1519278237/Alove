import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

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
                (const String.fromEnvironment(
                  'API_BASE_URL',
                  defaultValue: '',
                ).isNotEmpty
                    ? const String.fromEnvironment('API_BASE_URL')
                    : (kIsWeb
                        ? 'http://127.0.0.1:8000/api/v1'
                        : 'http://10.0.2.2:8000/api/v1')),
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

  Future<Map<String, dynamic>> exportMyData() => _get('/me/export');

  Future<List<Map<String, dynamic>>> dataAccessHistory() =>
      _getList('/data-access-history');

  Future<Map<String, dynamic>> updateProfile(Map<String, dynamic> data) =>
      _patch('/me/profile', data);

  Future<void> deleteAccount() => _delete('/me');

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

  Future<List<Map<String, dynamic>>> familyInvites(String familyId) {
    return _getList('/families/$familyId/invites');
  }

  Future<Map<String, dynamic>> createConversation(String familyId) {
    return _post('/conversations', {
      'family_id': familyId,
      'sharing_level': 'private',
    });
  }

  Future<Map<String, dynamic>> sendMessage(
    String conversationId,
    String text, {
    String? imageMediaId,
  }) {
    return _post('/conversations/$conversationId/messages', {
      'text': text,
      'image_media_id': imageMediaId,
    });
  }

  Future<Map<String, dynamic>> setConversationSharing(
    String conversationId,
    String level,
  ) {
    return _post('/conversations/$conversationId/sharing-level', {
      'sharing_level': level,
    });
  }

  Future<List<Map<String, dynamic>>> conversations() =>
      _getList('/conversations');

  Future<Map<String, dynamic>> endConversation(String conversationId) =>
      _post('/conversations/$conversationId/end', const {});

  Future<List<Map<String, dynamic>>> inbox() =>
      _getList('/family-messages/inbox');

  Future<List<Map<String, dynamic>>> sentMessages() =>
      _getList('/family-messages/sent');

  Future<Map<String, dynamic>> sendFamilyMessage({
    required String recipientUserId,
    required String content,
    String type = 'text',
    String? audioObjectKey,
  }) =>
      _post('/family-messages', {
        'recipient_user_id': recipientUserId,
        'type': type,
        'content': content,
        'audio_object_key': audioObjectKey,
      });

  Future<Map<String, dynamic>> markMessagePlayed(String messageId) =>
      _post('/family-messages/$messageId/played', const {});

  Future<Map<String, dynamic>> uploadAudio({
    required Uint8List bytes,
    required String filename,
  }) async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/media/audio',
      data: FormData.fromMap({
        'file': MultipartFile.fromBytes(bytes, filename: filename),
      }),
      options: Options(contentType: 'multipart/form-data'),
    );
    return response.data ?? <String, dynamic>{};
  }

  Future<Map<String, dynamic>> uploadImage({
    required Uint8List bytes,
    required String filename,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/media/image',
        data: FormData.fromMap({
          'file': MultipartFile.fromBytes(bytes, filename: filename),
        }),
        options: Options(contentType: 'multipart/form-data'),
      );
      return response.data ?? <String, dynamic>{};
    } on DioException catch (error) {
      throw _apiException(error);
    }
  }

  Future<Uint8List> downloadMedia(String mediaId) async {
    final response = await _dio.get<List<int>>(
      '/media/$mediaId',
      options: Options(responseType: ResponseType.bytes),
    );
    return Uint8List.fromList(response.data ?? const []);
  }

  Future<List<Map<String, dynamic>>> reminders() => _getList('/reminders');

  Future<Map<String, dynamic>> createReminder({
    required String ownerUserId,
    required String content,
    required String scheduleRule,
    String category = 'life',
  }) =>
      _post('/reminders', {
        'owner_user_id': ownerUserId,
        'content': content,
        'schedule_rule': scheduleRule,
        'category': category,
      });

  Future<Map<String, dynamic>> reminderAction(
    String reminderId,
    String action, {
    String? note,
  }) =>
      _post('/reminders/$reminderId/actions', {
        'action': action,
        'note': note,
      });

  Future<List<Map<String, dynamic>>> elderNeeds(String elderId) =>
      _getList('/elders/$elderId/needs');

  Future<List<Map<String, dynamic>>> elderReports(String elderId) =>
      _getList('/elders/$elderId/care-reports');

  Future<Map<String, dynamic>> generateReport(String elderId) =>
      _post('/elders/$elderId/care-reports/generate', {'period_days': 7});

  Future<Map<String, dynamic>> reportFeedback(
    String reportId,
    String feedback,
  ) =>
      _post('/care-reports/$reportId/feedback', {'feedback': feedback});

  Future<Map<String, dynamic>> createCareNeed({
    required String elderUserId,
    required String title,
    required String description,
    required String consentId,
    String priority = 'normal',
  }) =>
      _post('/care-needs', {
        'elder_user_id': elderUserId,
        'title': title,
        'description': description,
        'priority': priority,
        'consent_id': consentId,
      });

  Future<Map<String, dynamic>> acceptCareNeed(String needId) =>
      _post('/care-needs/$needId/accept', const {});

  Future<Map<String, dynamic>> completeCareNeed(String needId) =>
      _post('/care-needs/$needId/complete', const {});

  Future<List<Map<String, dynamic>>> consents() => _getList('/consents');

  Future<Map<String, dynamic>> createConsent({
    required String subjectUserId,
    required String familyId,
    required String consentType,
    String? granteeUserId,
    Map<String, dynamic>? scope,
  }) =>
      _post('/consents', {
        'subject_user_id': subjectUserId,
        'grantee_user_id': granteeUserId,
        'family_id': familyId,
        'consent_type': consentType,
        'scope': scope ?? <String, dynamic>{},
        'policy_version': 'v1.0',
      });

  Future<Map<String, dynamic>> revokeConsent(String consentId) =>
      _post('/consents/$consentId/revoke', const {});

  Future<List<Map<String, dynamic>>> knowledge(String familyId) =>
      _getList('/families/$familyId/knowledge');

  Future<Map<String, dynamic>> createKnowledge({
    required String familyId,
    required String title,
    required String content,
    String visibilityScope = 'family',
  }) =>
      _post('/families/$familyId/knowledge', {
        'title': title,
        'content': content,
        'source_type': 'manual',
        'visibility_scope': visibilityScope,
      });

  Future<void> deleteKnowledge(String documentId) =>
      _delete('/knowledge/$documentId');

  Future<List<Map<String, dynamic>>> memories() => _getList('/memories');

  Future<Map<String, dynamic>> createMemory({
    required String familyId,
    required String content,
    String memoryType = 'fact',
  }) =>
      _post('/memories', {
        'family_id': familyId,
        'memory_type': memoryType,
        'content': content,
        'sensitivity': 'normal',
        'sharing_level': 'private',
      });

  Future<Map<String, dynamic>> confirmMemory(String memoryId) =>
      _post('/memories/$memoryId/confirm', const {});

  Future<Map<String, dynamic>> rejectMemory(String memoryId) =>
      _post('/memories/$memoryId/reject', const {});

  Future<void> deleteMemory(String memoryId) => _delete('/memories/$memoryId');

  Future<List<Map<String, dynamic>>> styleProfiles(String familyId) =>
      _getList('/families/$familyId/style-profiles');

  Future<Map<String, dynamic>> saveStyleProfile({
    required String familyId,
    required String targetUserId,
    required String callingName,
    required List<String> greetings,
    required String sentenceStyle,
    required String comfortStyle,
    required String reminderStyle,
    required List<String> bannedPhrases,
  }) =>
      _put('/families/$familyId/style-profile', {
        'target_user_id': targetUserId,
        'preferred_calling_name': callingName,
        'common_greetings': greetings,
        'sentence_style': sentenceStyle,
        'dialect_preference': '普通话',
        'comfort_style': comfortStyle,
        'reminder_style': reminderStyle,
        'banned_phrases': bannedPhrases,
      });

  Future<List<Map<String, dynamic>>> voiceProfiles() =>
      _getList('/voice-profiles');

  Future<Map<String, dynamic>> createVoiceEnrollment({
    required String consentId,
    required List<String> allowedRecipientIds,
  }) =>
      _post('/voice-profiles/enrollment', {
        'consent_id': consentId,
        'provider': 'neutral-device-tts',
        'allowed_recipient_ids': allowedRecipientIds,
      });

  Future<Map<String, dynamic>> adminOverview(String familyId) =>
      _get('/admin/families/$familyId/overview');

  Future<List<Map<String, dynamic>>> riskEvents(String familyId) =>
      _getList('/admin/families/$familyId/risk-events');

  Future<Map<String, dynamic>> resolveRisk(
    String eventId,
    String resolution,
  ) =>
      _post('/admin/risk-events/$eventId/resolve', {
        'status': 'resolved',
        'resolution': resolution,
      });

  Future<List<Map<String, dynamic>>> auditLogs(String familyId) =>
      _getList('/admin/families/$familyId/audit-logs');

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

  Future<Map<String, dynamic>> _put(
    String path,
    Map<String, dynamic> data,
  ) async {
    try {
      final response = await _dio.put<Map<String, dynamic>>(path, data: data);
      return response.data ?? <String, dynamic>{};
    } on DioException catch (error) {
      throw _apiException(error);
    }
  }

  Future<Map<String, dynamic>> _patch(
    String path,
    Map<String, dynamic> data,
  ) async {
    try {
      final response = await _dio.patch<Map<String, dynamic>>(path, data: data);
      return response.data ?? <String, dynamic>{};
    } on DioException catch (error) {
      throw _apiException(error);
    }
  }

  Future<void> _delete(String path) async {
    try {
      await _dio.delete<void>(path);
    } on DioException catch (error) {
      throw _apiException(error);
    }
  }

  ApiException _apiException(DioException error) {
    return error.error is ApiException
        ? error.error as ApiException
        : ApiException('NETWORK_ERROR', '网络连接失败，请检查后端服务');
  }
}
