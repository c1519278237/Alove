import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/session.dart';

class CareNeedScreen extends ConsumerStatefulWidget {
  const CareNeedScreen({super.key});

  @override
  ConsumerState<CareNeedScreen> createState() => _CareNeedScreenState();
}

class _CareNeedScreenState extends ConsumerState<CareNeedScreen> {
  final _title = TextEditingController();
  final _description = TextEditingController();
  bool _busy = false;
  String _priority = 'normal';
  String? _error;

  @override
  void dispose() {
    _title.dispose();
    _description.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final session = ref.read(sessionProvider);
    if (_title.text.trim().isEmpty || _description.text.trim().isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      final consents = await api.consents();
      final consent = consents.cast<Map<String, dynamic>?>().firstWhere(
            (item) =>
                item?['consent_type'] == 'care_need_sharing' &&
                item?['revoked_at'] == null,
            orElse: () => null,
          );
      if (consent == null) {
        throw Exception('请先在“授权与我的数据”中开启“向家人转达需求”授权');
      }
      await api.createCareNeed(
        elderUserId: session.userId!,
        title: _title.text.trim(),
        description: _description.text.trim(),
        consentId: consent['id'] as String,
        priority: _priority,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('需求已按您的确认转达给家人')),
      );
      Navigator.pop(context);
    } catch (error) {
      setState(() => _error = error.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('请家人帮个忙')),
      body: ListView(
        padding: const EdgeInsets.all(22),
        children: [
          const Text('发送前请确认具体内容。归音不会替您添加未说过的信息。'),
          const SizedBox(height: 18),
          TextField(
            controller: _title,
            style: const TextStyle(fontSize: 20),
            decoration: const InputDecoration(
              labelText: '需要家人做什么',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _description,
            minLines: 3,
            maxLines: 6,
            style: const TextStyle(fontSize: 19),
            decoration: const InputDecoration(
              labelText: '补充说明',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'low', label: Text('不着急')),
              ButtonSegment(value: 'normal', label: Text('一般')),
              ButtonSegment(value: 'high', label: Text('较急')),
            ],
            selected: {_priority},
            onSelectionChanged: (value) =>
                setState(() => _priority = value.first),
          ),
          if (_error != null) ...[
            const SizedBox(height: 16),
            Text(_error!, style: const TextStyle(color: Colors.red)),
          ],
          const SizedBox(height: 24),
          FilledButton.icon(
            onPressed: _busy ? null : _submit,
            icon: const Icon(Icons.send),
            label: const Text('确认并转达'),
          ),
        ],
      ),
    );
  }
}
