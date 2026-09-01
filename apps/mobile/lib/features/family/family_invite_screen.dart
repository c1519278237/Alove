import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/child_navigation_bar.dart';
import '../../core/session.dart';

class FamilyInviteScreen extends ConsumerStatefulWidget {
  const FamilyInviteScreen({super.key});

  @override
  ConsumerState<FamilyInviteScreen> createState() => _FamilyInviteScreenState();
}

class _FamilyInviteScreenState extends ConsumerState<FamilyInviteScreen> {
  bool _loading = true;
  bool _busy = false;
  String? _error;
  List<Map<String, dynamic>> _members = const [];
  List<Map<String, dynamic>> _invites = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final familyId = ref.read(sessionProvider).familyId;
    if (familyId == null) {
      if (mounted) {
        setState(() {
          _loading = false;
          _error = '尚未读取到家庭信息，请返回首页后重试';
        });
      }
      return;
    }
    try {
      final api = ref.read(apiClientProvider);
      final results = await Future.wait([
        api.familyMembers(familyId),
        api.familyInvites(familyId),
      ]);
      _members = results[0];
      _invites = results[1];
      _error = null;
    } catch (error) {
      _error = error.toString();
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _createInvite() async {
    final familyId = ref.read(sessionProvider).familyId;
    if (familyId == null || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await ref.read(apiClientProvider).createInvite(
            familyId,
            role: 'elder',
            relationshipLabel: '父母',
          );
      await _load();
      if (!mounted) return;
      final code = result['code']?.toString() ?? '';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('新邀请码 $code 已生成，24小时内有效')),
      );
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _copyCode(String code) async {
    await Clipboard.setData(ClipboardData(text: code));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('邀请码已复制')),
    );
  }

  String _expiryText(Object? value) {
    final parsed = DateTime.tryParse(value?.toString() ?? '')?.toLocal();
    if (parsed == null) return '24小时内有效';
    String two(int number) => number.toString().padLeft(2, '0');
    return '有效至 ${parsed.month}月${parsed.day}日 ${two(parsed.hour)}:${two(parsed.minute)}';
  }

  String _roleLabel(Object? role) {
    return switch (role?.toString()) {
      'admin' => '管理员',
      'elder' => '老人',
      'caregiver' => '照护者',
      _ => '子女',
    };
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('家庭成员与邀请')),
      bottomNavigationBar: const ChildNavigationBar(
        current: ChildSection.invite,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(20),
                children: [
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text(
                            '邀请老人加入',
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
                          const SizedBox(height: 8),
                          const Text('每位老人使用独立手机号和独立邀请码加入；邀请码24小时有效且只能使用一次。'),
                          const SizedBox(height: 16),
                          FilledButton.icon(
                            onPressed: _busy ? null : _createInvite,
                            icon: const Icon(Icons.person_add_alt_1),
                            label: const Text('生成新的老人邀请码'),
                          ),
                          if (_busy) ...[
                            const SizedBox(height: 10),
                            const LinearProgressIndicator(),
                          ],
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text('当前有效邀请码',
                      style: Theme.of(context).textTheme.titleLarge),
                  if (_invites.isEmpty)
                    const Card(
                      child: ListTile(title: Text('暂无未使用的邀请码')),
                    ),
                  ..._invites.map((invite) {
                    final code = invite['code']?.toString() ?? '';
                    return Card(
                      child: ListTile(
                        leading: const Icon(Icons.vpn_key_outlined),
                        title: SelectableText(
                          code,
                          style: const TextStyle(
                            fontSize: 26,
                            fontWeight: FontWeight.bold,
                            letterSpacing: 2,
                          ),
                        ),
                        subtitle: Text(_expiryText(invite['expires_at'])),
                        trailing: IconButton(
                          tooltip: '复制邀请码',
                          onPressed: () => _copyCode(code),
                          icon: const Icon(Icons.copy),
                        ),
                      ),
                    );
                  }),
                  const SizedBox(height: 22),
                  Text('家庭成员', style: Theme.of(context).textTheme.titleLarge),
                  ..._members.map(
                    (member) => Card(
                      child: ListTile(
                        leading: Icon(
                          member['role'] == 'elder'
                              ? Icons.elderly
                              : Icons.person,
                        ),
                        title:
                            Text(member['display_name']?.toString() ?? '家庭成员'),
                        subtitle: Text(
                          '${_roleLabel(member['role'])} · ${member['relationship_label'] ?? '家庭成员'}',
                        ),
                      ),
                    ),
                  ),
                  if (_error != null)
                    Card(
                      color: const Color(0xFFFFF1D8),
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Text(_error!),
                      ),
                    ),
                ],
              ),
            ),
    );
  }
}
