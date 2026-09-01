import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/session.dart';

class QuickCallScreen extends ConsumerStatefulWidget {
  const QuickCallScreen({super.key});

  @override
  ConsumerState<QuickCallScreen> createState() => _QuickCallScreenState();
}

class _QuickCallScreenState extends ConsumerState<QuickCallScreen> {
  bool _loading = true;
  bool _busy = false;
  String? _error;
  List<Map<String, dynamic>> _contacts = const [];
  List<Map<String, dynamic>> _events = const [];

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
        api.familyContacts(familyId),
        api.callEvents(familyId),
      ]);
      _contacts = results[0]
          .where((item) => item['role'] != 'elder')
          .toList();
      _events = results[1];
    } catch (error) {
      _error = error.toString();
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _call(Map<String, dynamic> contact) async {
    if (_busy) return;
    final familyId = ref.read(sessionProvider).familyId;
    final phone = contact['phone']?.toString() ?? '';
    if (familyId == null || phone.isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      final event = await api.createCallEvent(
        familyId,
        contact['user_id'] as String,
      );
      final launched = await launchUrl(
        Uri(scheme: 'tel', path: phone),
        mode: LaunchMode.externalApplication,
      );
      if (!launched) {
        await api.finishCallEvent(event['id'] as String, status: 'failed');
        throw Exception('手机没有可用的拨号应用');
      }
      await _load();
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _markCompleted(String eventId) async {
    setState(() => _busy = true);
    try {
      await ref.read(apiClientProvider).finishCallEvent(eventId);
      await _load();
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('快捷联系家人')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(20),
                children: [
                  const Text(
                    '点击家人即可打开手机拨号。这里只记录从归音发起的呼叫，不读取您的系统通话记录。',
                    style: TextStyle(fontSize: 18),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!, style: const TextStyle(color: Colors.red)),
                  ],
                  if (_busy) const LinearProgressIndicator(),
                  const SizedBox(height: 18),
                  if (_contacts.isEmpty) const Text('家庭中还没有可快捷呼叫的子女或照护人'),
                  ..._contacts.map(
                    (contact) => Card(
                      child: ListTile(
                        minVerticalPadding: 18,
                        leading: const CircleAvatar(
                          child: Icon(Icons.person, size: 30),
                        ),
                        title: Text(
                          contact['display_name']?.toString() ?? '家人',
                          style: const TextStyle(
                            fontSize: 23,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        subtitle: Text(
                          '${contact['relationship_label'] ?? '家庭成员'}\n${contact['phone'] ?? ''}',
                        ),
                        isThreeLine: true,
                        trailing: FilledButton.icon(
                          onPressed: _busy ? null : () => _call(contact),
                          icon: const Icon(Icons.phone),
                          label: const Text('呼叫'),
                        ),
                      ),
                    ),
                  ),
                  const Divider(height: 40),
                  Text('最近呼叫', style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: 8),
                  if (_events.isEmpty) const Text('暂无呼叫记录'),
                  ..._events.take(20).map(
                    (event) => ListTile(
                      leading: const Icon(Icons.history),
                      title: Text(
                        '${event['caller_name'] ?? '家人'} → ${event['callee_name'] ?? '家人'}',
                      ),
                      subtitle: Text(event['created_at']?.toString() ?? ''),
                      trailing: event['status'] == 'initiated' &&
                              event['caller_user_id'] ==
                                  ref.read(sessionProvider).userId
                          ? TextButton(
                              onPressed: _busy
                                  ? null
                                  : () => _markCompleted(event['id'] as String),
                              child: const Text('标记完成'),
                            )
                          : Text(event['status']?.toString() ?? ''),
                    ),
                  ),
                ],
              ),
            ),
    );
  }
}
