import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/child_navigation_bar.dart';
import '../../core/session.dart';

class AdminDashboardScreen extends ConsumerStatefulWidget {
  const AdminDashboardScreen({super.key});

  @override
  ConsumerState<AdminDashboardScreen> createState() =>
      _AdminDashboardScreenState();
}

class _AdminDashboardScreenState extends ConsumerState<AdminDashboardScreen> {
  bool _loading = true;
  String? _error;
  Map<String, dynamic>? _overview;
  List<Map<String, dynamic>> _risks = const [];
  List<Map<String, dynamic>> _audits = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final familyId = ref.read(sessionProvider).familyId;
    if (familyId == null) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      final results = await Future.wait([
        api.adminOverview(familyId),
        api.riskEvents(familyId),
        api.auditLogs(familyId),
      ]);
      _overview = results[0] as Map<String, dynamic>;
      _risks = results[1] as List<Map<String, dynamic>>;
      _audits = results[2] as List<Map<String, dynamic>>;
    } catch (error) {
      _error = error.toString();
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _resolve(String eventId) async {
    final controller = TextEditingController();
    final resolution = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('记录处理结果'),
        content: TextField(
          controller: controller,
          minLines: 2,
          maxLines: 5,
          decoration: const InputDecoration(
            hintText: '例如：已电话联系老人并确认安全',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context), child: const Text('取消')),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('保存'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (resolution == null || resolution.isEmpty) return;
    try {
      await ref.read(apiClientProvider).resolveRisk(eventId, resolution);
      await _load();
    } catch (error) {
      setState(() => _error = error.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('运营与安全面板')),
      bottomNavigationBar: const ChildNavigationBar(
        current: ChildSection.admin,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(18),
                children: [
                  if (_error != null)
                    Card(
                      color: const Color(0xFFFFF1D8),
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Text(_error!),
                      ),
                    ),
                  if (_overview != null) _overviewGrid(),
                  const SizedBox(height: 20),
                  Text('风险事件', style: Theme.of(context).textTheme.titleLarge),
                  const Text('后台只展示风险标签和脱敏摘要，不直接展示完整对话。'),
                  if (_risks.isEmpty) const ListTile(title: Text('暂无风险事件')),
                  ..._risks.map(
                    (risk) => Card(
                      child: ListTile(
                        leading: Icon(
                          risk['level'] == 'high'
                              ? Icons.warning_amber
                              : Icons.info_outline,
                          color: risk['level'] == 'high'
                              ? Colors.red
                              : Colors.orange,
                        ),
                        title: Text((risk['labels'] as List).join('、')),
                        subtitle:
                            Text('${risk['summary']}\n状态：${risk['status']}'),
                        isThreeLine: true,
                        trailing: risk['status'] == 'open'
                            ? TextButton(
                                onPressed: () => _resolve(risk['id'] as String),
                                child: const Text('处理'),
                              )
                            : const Icon(Icons.check),
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),
                  Text('最近审计日志', style: Theme.of(context).textTheme.titleLarge),
                  ..._audits.take(30).map(
                        (item) => ListTile(
                          dense: true,
                          leading: const Icon(Icons.history),
                          title: Text(item['action']?.toString() ?? ''),
                          subtitle: Text(
                              '${item['resource_type']} · ${item['reason']}'),
                        ),
                      ),
                ],
              ),
            ),
    );
  }

  Widget _overviewGrid() {
    final items = <(String, String, IconData)>[
      ('家庭成员', '${_overview!['active_members']}', Icons.group),
      ('老人用户', '${_overview!['elders']}', Icons.elderly),
      ('7日对话', '${_overview!['conversations_7d']}', Icons.forum),
      ('7日消息', '${_overview!['messages_7d']}', Icons.message),
      ('待处理风险', '${_overview!['open_risk_events']}', Icons.warning),
      ('待办需求', '${_overview!['pending_care_needs']}', Icons.task_alt),
      ('AI Token', '${_overview!['ai_tokens_7d']}', Icons.auto_awesome),
      (
        '估算成本',
        '\$${(_overview!['estimated_cost_usd_7d'] as num).toStringAsFixed(4)}',
        Icons.payments,
      ),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('系统概览', style: Theme.of(context).textTheme.titleLarge),
        Text('模型：${_overview!['ai_provider']} / ${_overview!['ai_model']}'),
        const SizedBox(height: 12),
        GridView.count(
          crossAxisCount: MediaQuery.sizeOf(context).width > 700 ? 4 : 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          childAspectRatio: 1.6,
          children: items
              .map(
                (item) => Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(item.$3),
                        Text(item.$2,
                            style: const TextStyle(
                                fontSize: 22, fontWeight: FontWeight.bold)),
                        Text(item.$1),
                      ],
                    ),
                  ),
                ),
              )
              .toList(),
        ),
      ],
    );
  }
}
