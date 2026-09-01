import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/session.dart';

class ElderManageScreen extends ConsumerStatefulWidget {
  const ElderManageScreen({super.key});

  @override
  ConsumerState<ElderManageScreen> createState() => _ElderManageScreenState();
}

class _ElderManageScreenState extends ConsumerState<ElderManageScreen> {
  static const _consentLabels = <String, String>{
    'conversation_summary': '家庭关怀摘要',
    'care_need_sharing': '向家人转达需求',
    'reminder_management': '家人为我创建提醒',
    'family_knowledge': '使用家庭知识库',
    'style_personalization': '使用家人的表达习惯',
    'voice_use': '声线授权演示',
    'audio_retention': '保留语音录音',
  };

  bool _loading = true;
  bool _busy = false;
  String? _error;
  String? _granteeId;
  List<Map<String, dynamic>> _members = const [];
  List<Map<String, dynamic>> _consents = const [];
  List<Map<String, dynamic>> _memories = const [];
  final _memoryInput = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _memoryInput.dispose();
    super.dispose();
  }

  Future<void> _load({bool showSpinner = true}) async {
    final session = ref.read(sessionProvider);
    if (session.familyId == null) {
      if (mounted) {
        setState(() {
          _loading = false;
          _error = '尚未读取到家庭信息，请返回首页后重试';
        });
      }
      return;
    }
    if (showSpinner && mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final api = ref.read(apiClientProvider);
      final results = await Future.wait([
        api.familyMembers(session.familyId!),
        api.consents(),
        api.memories(),
      ]).timeout(const Duration(seconds: 12));
      _members = results[0]
          .where((item) => item['user_id'] != session.userId)
          .toList();
      _consents = results[1];
      _memories = results[2];
      _granteeId ??=
          _members.isEmpty ? null : _members.first['user_id'] as String?;
    } on TimeoutException {
      _error = '加载超过12秒，请检查后端服务后点击重试';
    } catch (error) {
      _error = error.toString();
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _runMutation(
    Future<void> Function() action, {
    required String success,
  }) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action().timeout(const Duration(seconds: 12));
      await _load(showSpinner: false);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(success)),
      );
    } on TimeoutException {
      if (mounted) setState(() => _error = '操作超过12秒，请确认后端服务正常后重试');
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  bool _active(Map<String, dynamic> consent) => consent['revoked_at'] == null;

  Map<String, dynamic>? _activeConsent(String type) {
    for (final consent in _consents) {
      if (consent['consent_type'] == type && _active(consent)) return consent;
    }
    return null;
  }

  Future<void> _grant(String type) async {
    final session = ref.read(sessionProvider);
    if (_granteeId == null ||
        session.userId == null ||
        session.familyId == null) {
      setState(() => _error = '家庭中还没有可授权的家人');
      return;
    }
    await _runMutation(() async {
      await ref.read(apiClientProvider).createConsent(
        subjectUserId: session.userId!,
        familyId: session.familyId!,
        granteeUserId: _granteeId,
        consentType: type,
        scope: {
          'summary_only': type == 'conversation_summary',
          'explicit_confirmation_required': true,
        },
      );
    }, success: '授权已保存');
  }

  Future<void> _revoke(String consentId) async {
    await _runMutation(() async {
      await ref.read(apiClientProvider).revokeConsent(consentId);
    }, success: '授权已撤回');
  }

  Future<void> _memoryAction(String id, String action) async {
    await _runMutation(() async {
      final api = ref.read(apiClientProvider);
      if (action == 'confirm') await api.confirmMemory(id);
      if (action == 'reject') await api.rejectMemory(id);
      if (action == 'delete') await api.deleteMemory(id);
    }, success: action == 'delete' ? '记忆已删除' : '记忆状态已更新');
  }

  Future<void> _addMemory() async {
    final content = _memoryInput.text.trim();
    final familyId = ref.read(sessionProvider).familyId;
    if (content.isEmpty || familyId == null) return;
    await _runMutation(() async {
      await ref.read(apiClientProvider).createMemory(
            familyId: familyId,
            content: content,
          );
      _memoryInput.clear();
    }, success: '记忆已添加，请确认后再供AI使用');
  }

  Future<void> _deleteAccount() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('确认删除账号？'),
        content: const Text('对话、记忆、资料和声线关联数据将被清理，此操作无法直接恢复。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('确认删除'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    await ref.read(apiClientProvider).deleteAccount();
    await ref.read(sessionProvider.notifier).logout();
  }

  Future<void> _showExport() async {
    try {
      final payload = await ref.read(apiClientProvider).exportMyData();
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('我的数据副本'),
          content: SizedBox(
            width: 700,
            child: SingleChildScrollView(
              child: SelectableText(
                const JsonEncoder.withIndent('  ').convert(payload),
              ),
            ),
          ),
          actions: [
            FilledButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('完成'),
            ),
          ],
        ),
      );
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('授权与我的数据'),
          bottom: const TabBar(
            tabs: [
              Tab(text: '授权'),
              Tab(text: '记忆'),
              Tab(text: '账号'),
            ],
          ),
        ),
        body: _loading
            ? const Center(child: CircularProgressIndicator())
            : Column(
                children: [
                  if (_error != null)
                    MaterialBanner(
                      content: Text(_error!),
                      actions: [
                        TextButton(onPressed: _load, child: const Text('重试')),
                      ],
                    ),
                  if (_busy) const LinearProgressIndicator(),
                  Expanded(
                    child: TabBarView(
                      children: [
                        _buildConsents(),
                        _buildMemories(),
                        _buildAccount(),
                      ],
                    ),
                  ),
                ],
              ),
      ),
    );
  }

  Widget _buildConsents() {
    return ListView(
      padding: const EdgeInsets.all(18),
      children: [
        const Text('授权可以随时撤回。未授权的对话不会进入家属摘要。'),
        const SizedBox(height: 14),
        DropdownButtonFormField<String>(
          initialValue: _granteeId,
          decoration: const InputDecoration(
            labelText: '授权给哪位家人',
            border: OutlineInputBorder(),
          ),
          items: _members
              .map(
                (member) => DropdownMenuItem(
                  value: member['user_id'] as String,
                  child: Text(member['display_name']?.toString() ?? '家庭成员'),
                ),
              )
              .toList(),
          onChanged: (value) => setState(() => _granteeId = value),
        ),
        const SizedBox(height: 14),
        ..._consentLabels.entries.map((entry) {
          final consent = _activeConsent(entry.key);
          return Card(
            child: ListTile(
              title: Text(entry.value),
              subtitle: Text(consent == null ? '未授权' : '已授权，可随时撤回'),
              trailing: consent == null
                  ? FilledButton.tonal(
                      onPressed: _busy ? null : () => _grant(entry.key),
                      child: const Text('授权'),
                    )
                  : TextButton(
                      onPressed:
                          _busy ? null : () => _revoke(consent['id'] as String),
                      child: const Text('撤回'),
                    ),
            ),
          );
        }),
      ],
    );
  }

  Widget _buildMemories() {
    return ListView(
      padding: const EdgeInsets.all(18),
      children: [
        const Text('AI 只能使用您确认过的记忆。候选记忆可以确认、拒绝或删除。'),
        const SizedBox(height: 14),
        TextField(
          controller: _memoryInput,
          decoration: InputDecoration(
            labelText: '手动添加一条记忆',
            border: const OutlineInputBorder(),
            suffixIcon: IconButton(
              onPressed: _busy ? null : _addMemory,
              icon: const Icon(Icons.add),
            ),
          ),
        ),
        const SizedBox(height: 14),
        if (_memories.isEmpty) const Text('暂无记忆'),
        ..._memories.map((memory) {
          final pending = memory['confirmation_status'] == 'pending';
          return Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(memory['content']?.toString() ?? ''),
                  Text('状态：${memory['confirmation_status']}'),
                  Wrap(
                    children: [
                      if (pending)
                        TextButton(
                          onPressed: () =>
                              _memoryAction(memory['id'] as String, 'confirm'),
                          child: const Text('确认'),
                        ),
                      if (pending)
                        TextButton(
                          onPressed: () =>
                              _memoryAction(memory['id'] as String, 'reject'),
                          child: const Text('不是这样'),
                        ),
                      TextButton(
                        onPressed: _busy
                            ? null
                            : () => _memoryAction(
                                  memory['id'] as String,
                                  'delete',
                                ),
                        child: const Text('删除'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          );
        }),
      ],
    );
  }

  Widget _buildAccount() {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        const ListTile(
          leading: Icon(Icons.privacy_tip_outlined),
          title: Text('数据保护'),
          subtitle: Text('手机号、对话、记忆和需求均由服务端加密保存。'),
        ),
        const ListTile(
          leading: Icon(Icons.smart_toy_outlined),
          title: Text('AI 身份'),
          subtitle: Text('归音始终是 AI 助手，不是真实子女、医生或紧急服务。'),
        ),
        FutureBuilder<List<Map<String, dynamic>>>(
          future: ref.read(apiClientProvider).dataAccessHistory(),
          builder: (context, snapshot) {
            final rows = snapshot.data ?? const [];
            return ExpansionTile(
              leading: const Icon(Icons.history),
              title: const Text('数据访问记录'),
              subtitle:
                  Text(rows.isEmpty ? '暂无记录或正在加载' : '最近 ${rows.length} 条记录'),
              children: rows
                  .take(20)
                  .map(
                    (item) => ListTile(
                      dense: true,
                      title: Text(item['action']?.toString() ?? '数据访问'),
                      subtitle: Text(item['created_at']?.toString() ?? ''),
                    ),
                  )
                  .toList(),
            );
          },
        ),
        const SizedBox(height: 24),
        OutlinedButton.icon(
          onPressed: _showExport,
          icon: const Icon(Icons.download),
          label: const Text('查看并导出我的数据'),
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: _deleteAccount,
          icon: const Icon(Icons.delete_forever),
          label: const Text('删除账号和个人数据'),
        ),
      ],
    );
  }
}
