import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/session.dart';

class FamilySetupScreen extends ConsumerStatefulWidget {
  const FamilySetupScreen({super.key});

  @override
  ConsumerState<FamilySetupScreen> createState() => _FamilySetupScreenState();
}

class _FamilySetupScreenState extends ConsumerState<FamilySetupScreen> {
  final _familyName = TextEditingController();
  final _inviteCode = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _familyName.dispose();
    _inviteCode.dispose();
    super.dispose();
  }

  Future<void> _create() async {
    setState(() => _busy = true);
    try {
      await ref.read(apiClientProvider).createFamily(
            name: _familyName.text,
            role: 'admin',
          );
      await ref.read(sessionProvider.notifier).refreshFamilyContext();
    } catch (error) {
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _join() async {
    setState(() => _busy = true);
    try {
      await ref
          .read(apiClientProvider)
          .acceptInvite(_inviteCode.text.trim().toUpperCase());
      await ref.read(sessionProvider.notifier).refreshFamilyContext();
    } catch (error) {
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('建立家庭连接')),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          const Text('子女或管理员创建家庭后，再邀请老人加入。'),
          const SizedBox(height: 20),
          TextField(
            controller: _familyName,
            decoration: const InputDecoration(
              labelText: '家庭名称，例如“林家”',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: _busy ? null : _create,
            child: const Text('创建家庭'),
          ),
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 24),
            child: Divider(),
          ),
          TextField(
            controller: _inviteCode,
            textCapitalization: TextCapitalization.characters,
            decoration: const InputDecoration(
              labelText: '8位家庭邀请码',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          OutlinedButton(
            onPressed: _busy ? null : _join,
            child: const Padding(
              padding: EdgeInsets.all(14),
              child: Text('加入家庭', style: TextStyle(fontSize: 20)),
            ),
          ),
          if (_error != null) ...[
            const SizedBox(height: 16),
            Text(_error!, style: const TextStyle(color: Colors.red)),
          ],
        ],
      ),
    );
  }
}
