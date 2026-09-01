import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/child_navigation_bar.dart';
import '../../core/session.dart';

class ChildHomeScreen extends ConsumerStatefulWidget {
  const ChildHomeScreen({super.key});

  @override
  ConsumerState<ChildHomeScreen> createState() => _ChildHomeScreenState();
}

class _ChildHomeScreenState extends ConsumerState<ChildHomeScreen> {
  bool _loading = true;
  String? _elderId;
  String? _elderName;
  String? _error;
  List<Map<String, dynamic>> _elders = const [];
  List<Map<String, dynamic>> _needs = const [];
  List<Map<String, dynamic>> _reports = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final familyId = ref.read(sessionProvider).familyId;
    if (familyId == null) return;
    if (mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final api = ref.read(apiClientProvider);
      final members = await api.familyMembers(familyId);
      _elders = members.where((member) => member['role'] == 'elder').toList();
      if (_elders.isNotEmpty) {
        final selected = _elders.cast<Map<String, dynamic>?>().firstWhere(
              (member) => member?['user_id'] == _elderId,
              orElse: () => _elders.first,
            )!;
        _elderId = selected['user_id'] as String;
        _elderName = selected['display_name']?.toString() ?? '老人';
        try {
          _needs = await api.elderNeeds(_elderId!);
          _reports = await api.elderReports(_elderId!);
        } on ApiException catch (error) {
          if (error.code != 'CONSENT_REQUIRED') rethrow;
          _error = '老人尚未授权查看需求或关怀摘要。请先当面说明用途并由老人本人授权。';
        }
      } else {
        _elderId = null;
        _elderName = null;
        _needs = const [];
        _reports = const [];
      }
    } catch (error) {
      _error = error.toString();
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _selectElder(String? elderId) async {
    if (elderId == null || elderId == _elderId) return;
    setState(() => _elderId = elderId);
    await _load();
  }

  Future<void> _generateReport() async {
    if (_elderId == null) return;
    try {
      await ref.read(apiClientProvider).generateReport(_elderId!);
      await _load();
    } catch (error) {
      setState(() => _error = error.toString());
    }
  }

  Future<void> _needAction(String id, String status) async {
    try {
      final api = ref.read(apiClientProvider);
      if (status == 'pending') {
        await api.acceptCareNeed(id);
      } else if (status == 'accepted') {
        await api.completeCareNeed(id);
      }
      await _load();
    } catch (error) {
      setState(() => _error = error.toString());
    }
  }

  Future<void> _reportFeedback(String id, String feedback) async {
    try {
      await ref.read(apiClientProvider).reportFeedback(id, feedback);
      await _load();
    } catch (error) {
      setState(() => _error = error.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text('家庭关怀 · ${session.displayName ?? ''}'),
        actions: [
          IconButton(
            tooltip: '退出登录',
            onPressed: () => ref.read(sessionProvider.notifier).logout(),
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      bottomNavigationBar: const ChildNavigationBar(
        current: ChildSection.home,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(20),
                children: [
                  if (_elderId == null) _buildInviteCard(context),
                  if (_elderId != null) ...[
                    if (_elders.length > 1) ...[
                      DropdownButtonFormField<String>(
                        initialValue: _elderId,
                        decoration: const InputDecoration(
                          labelText: '当前查看的老人',
                          border: OutlineInputBorder(),
                          prefixIcon: Icon(Icons.elderly),
                        ),
                        items: _elders
                            .map(
                              (elder) => DropdownMenuItem(
                                value: elder['user_id'] as String,
                                child: Text(
                                  elder['display_name']?.toString() ?? '老人',
                                ),
                              ),
                            )
                            .toList(),
                        onChanged: _selectElder,
                      ),
                      const SizedBox(height: 18),
                    ],
                    Text(
                      '$_elderName的近况',
                      style: Theme.of(context).textTheme.headlineSmall,
                    ),
                    const SizedBox(height: 8),
                    const Text('这里只展示老人明确授权的摘要，不展示未授权对话原文。'),
                    const SizedBox(height: 20),
                    _buildNeedsCard(context),
                    const SizedBox(height: 16),
                    _buildReportCard(context),
                    const SizedBox(height: 16),
                    FilledButton.tonalIcon(
                      onPressed: () => context.go('/family-tools'),
                      icon: const Icon(Icons.dashboard_customize),
                      label: const Text('留言、提醒、知识库与表达风格'),
                    ),
                    if (session.role == 'admin') ...[
                      const SizedBox(height: 12),
                      OutlinedButton.icon(
                        onPressed: () => context.go('/admin'),
                        icon: const Icon(Icons.security),
                        label: const Text('运营与安全面板'),
                      ),
                    ],
                  ],
                  if (_error != null) ...[
                    const SizedBox(height: 18),
                    Container(
                      padding: const EdgeInsets.all(16),
                      color: const Color(0xFFFFF1D8),
                      child: Text(_error!),
                    ),
                  ],
                ],
              ),
            ),
    );
  }

  Widget _buildInviteCard(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('邀请老人加入', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 10),
            const Text('邀请码 24 小时内有效。建议当面协助老人完成登录和身份确认。'),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: () => context.go('/family-invite'),
              icon: const Icon(Icons.person_add_alt_1),
              label: const Text('前往邀请与成员管理'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNeedsCard(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('待回应需求', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 10),
            if (_needs.isEmpty) const Text('暂无已授权转达的需求'),
            ..._needs.take(5).map(
                  (need) => ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.check_circle_outline),
                    title: Text(need['title']?.toString() ?? '一项需求'),
                    subtitle: Text(need['status']?.toString() ?? 'pending'),
                    trailing: need['status'] == 'pending' ||
                            need['status'] == 'accepted'
                        ? FilledButton.tonal(
                            onPressed: () => _needAction(
                              need['id'] as String,
                              need['status'] as String,
                            ),
                            child:
                                Text(need['status'] == 'pending' ? '接收' : '完成'),
                          )
                        : const Icon(Icons.check),
                  ),
                ),
          ],
        ),
      ),
    );
  }

  Widget _buildReportCard(BuildContext context) {
    final latest = _reports.isEmpty ? null : _reports.first;
    final report = latest?['report'] as Map?;
    final topics = report?['frequent_topics'] as List? ?? const [];
    final observations = report?['observations'] as List? ?? const [];
    final actions = report?['recommended_actions'] as List? ?? const [];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('生活状态与关怀摘要', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 10),
            Text(
              report?['disclaimer']?.toString() ?? '暂无摘要。生成前会再次校验老人的有效授权。',
            ),
            if (topics.isNotEmpty) ...[
              const SizedBox(height: 14),
              const Text(
                '近期常提主题',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
              for (final topic in topics.take(5))
                Text(
                  '• ${(topic as Map)['topic']}（${topic['mentions']} 次）',
                ),
            ],
            if (observations.isNotEmpty) ...[
              const SizedBox(height: 14),
              const Text(
                '客观观察',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
              for (final item in observations.take(5)) Text('• $item'),
            ],
            if (actions.isNotEmpty) ...[
              const SizedBox(height: 14),
              const Text(
                '建议家人行动',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
              for (final item in actions.take(5)) Text('• $item'),
            ],
            if (latest != null) ...[
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  const Text('摘要是否准确？'),
                  TextButton(
                    onPressed: () => _reportFeedback(
                      latest['id'] as String,
                      'accurate',
                    ),
                    child: const Text('准确'),
                  ),
                  TextButton(
                    onPressed: () => _reportFeedback(
                      latest['id'] as String,
                      'partly_accurate',
                    ),
                    child: const Text('部分准确'),
                  ),
                  TextButton(
                    onPressed: () => _reportFeedback(
                      latest['id'] as String,
                      'inaccurate',
                    ),
                    child: const Text('不准确'),
                  ),
                ],
              ),
            ],
            const SizedBox(height: 14),
            FilledButton(
              onPressed: _generateReport,
              child: const Text('生成本周摘要'),
            ),
          ],
        ),
      ),
    );
  }
}
