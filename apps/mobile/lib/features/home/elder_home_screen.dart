import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/session.dart';
import '../../core/notification_service.dart';

Future<List<Map<String, dynamic>>> _loadReminders(WidgetRef ref) async {
  final reminders = await ref.read(apiClientProvider).reminders();
  await NotificationService.instance.syncReminders(reminders);
  return reminders;
}

class ElderHomeScreen extends ConsumerWidget {
  const ElderHomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text('${session.displayName ?? '您好'}，今天想聊什么？'),
        actions: [
          IconButton(
            tooltip: '退出登录',
            onPressed: () => ref.read(sessionProvider.notifier).logout(),
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(22),
        children: [
          const _IdentityCard(),
          const SizedBox(height: 24),
          FilledButton.icon(
            onPressed: () => context.push('/conversation'),
            icon: const Icon(Icons.mic, size: 34),
            label: const Padding(
              padding: EdgeInsets.symmetric(vertical: 10),
              child: Text('和归音说说话'),
            ),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: FilledButton.tonalIcon(
                  onPressed: () => context.push('/care-need'),
                  icon: const Icon(Icons.volunteer_activism),
                  label: const Text('请家人帮忙'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton.tonalIcon(
                  onPressed: () => context.push('/elder-manage'),
                  icon: const Icon(Icons.privacy_tip),
                  label: const Text('授权与记忆'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),
          _HomeSection(
            icon: Icons.mark_unread_chat_alt_outlined,
            title: '家人留言',
            loader: () => ref.read(apiClientProvider).inbox(),
            emptyText: '暂时没有新留言',
            itemText: (item) => item['content']?.toString() ?? '一条家人留言',
            actionLabel: (item) {
              if (item['type'] == 'audio' && item['audio_object_key'] != null) {
                return '播放';
              }
              return item['played_at'] == null ? '我看到了' : null;
            },
            onAction: (item) async {
              final api = ref.read(apiClientProvider);
              if (item['type'] == 'audio' && item['audio_object_key'] != null) {
                final bytes = await api.downloadMedia(
                  item['audio_object_key'] as String,
                );
                final player = AudioPlayer();
                await player.play(BytesSource(bytes));
                player.onPlayerComplete.first.then((_) => player.dispose());
              }
              await api.markMessagePlayed(item['id'] as String);
            },
          ),
          const SizedBox(height: 18),
          _HomeSection(
            icon: Icons.notifications_active_outlined,
            title: '今天的提醒',
            loader: () => _loadReminders(ref),
            emptyText: '今天没有待办提醒',
            itemText: (item) => item['content']?.toString() ?? '一条提醒',
            actionLabel: (item) => item['status'] == 'active' ? '我完成了' : null,
            onAction: (item) async {
              await ref
                  .read(apiClientProvider)
                  .reminderAction(item['id'] as String, 'confirmed');
            },
          ),
          const SizedBox(height: 24),
          OutlinedButton.icon(
            onPressed: () => context.push('/quick-call'),
            icon: const Icon(Icons.phone, size: 28),
            label: const Padding(
              padding: EdgeInsets.all(12),
              child: Text('一键呼叫子女', style: TextStyle(fontSize: 20)),
            ),
          ),
        ],
      ),
    );
  }
}

class _IdentityCard extends StatelessWidget {
  const _IdentityCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFFE2F1EF),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFF65A9A2)),
      ),
      child: const Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.auto_awesome, size: 32, color: Color(0xFF176B7A)),
          SizedBox(width: 14),
          Expanded(
            child: Text(
              '我是归音 AI 助手，不是真实家人。我可以陪您聊天、整理提醒；涉及健康、钱款或紧急情况，请联系真实家人和专业人员。',
              style: TextStyle(fontSize: 19, height: 1.5),
            ),
          ),
        ],
      ),
    );
  }
}

class _HomeSection extends StatefulWidget {
  const _HomeSection({
    required this.icon,
    required this.title,
    required this.loader,
    required this.emptyText,
    required this.itemText,
    required this.actionLabel,
    required this.onAction,
  });

  final IconData icon;
  final String title;
  final Future<List<Map<String, dynamic>>> Function() loader;
  final String emptyText;
  final String Function(Map<String, dynamic>) itemText;
  final String? Function(Map<String, dynamic>) actionLabel;
  final Future<void> Function(Map<String, dynamic>) onAction;

  @override
  State<_HomeSection> createState() => _HomeSectionState();
}

class _HomeSectionState extends State<_HomeSection> {
  late Future<List<Map<String, dynamic>>> _future;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _future = widget.loader();
  }

  Future<void> _runAction(Map<String, dynamic> item) async {
    setState(() => _busy = true);
    try {
      await widget.onAction(item);
      if (mounted) setState(() => _future = widget.loader());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(widget.icon, size: 30),
                const SizedBox(width: 10),
                Text(widget.title,
                    style: Theme.of(context).textTheme.titleLarge),
              ],
            ),
            const SizedBox(height: 12),
            FutureBuilder<List<Map<String, dynamic>>>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const LinearProgressIndicator();
                }
                if (snapshot.hasError) {
                  return const Text('暂时无法加载，请稍后再试');
                }
                final items = snapshot.data ?? const [];
                if (items.isEmpty) return Text(widget.emptyText);
                return Column(
                  children: items
                      .take(3)
                      .map(
                        (item) => ListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Text(
                            widget.itemText(item),
                            style: const TextStyle(fontSize: 18),
                          ),
                          trailing: widget.actionLabel(item) == null
                              ? const Icon(Icons.check, color: Colors.green)
                              : FilledButton.tonal(
                                  onPressed:
                                      _busy ? null : () => _runAction(item),
                                  child: Text(widget.actionLabel(item)!),
                                ),
                        ),
                      )
                      .toList(),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}
