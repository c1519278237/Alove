import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:file_picker/file_picker.dart';

import '../../core/session.dart';

class FamilyToolsScreen extends ConsumerStatefulWidget {
  const FamilyToolsScreen({super.key});

  @override
  ConsumerState<FamilyToolsScreen> createState() => _FamilyToolsScreenState();
}

class _FamilyToolsScreenState extends ConsumerState<FamilyToolsScreen> {
  bool _loading = true;
  bool _busy = false;
  String? _error;
  String? _elderId;
  List<Map<String, dynamic>> _knowledge = const [];
  List<Map<String, dynamic>> _sent = const [];
  List<Map<String, dynamic>> _voiceProfiles = const [];

  final _message = TextEditingController();
  final _reminder = TextEditingController();
  final _schedule = TextEditingController(text: '每天 08:00');
  final _knowledgeTitle = TextEditingController();
  final _knowledgeContent = TextEditingController();
  final _callingName = TextEditingController(text: '妈妈');
  final _greetings = TextEditingController(text: '妈，今天感觉怎么样');
  final _sentenceStyle = TextEditingController(text: '短句、自然、温和');
  final _comfortStyle = TextEditingController(text: '先听完，再表示理解');
  final _reminderStyle = TextEditingController(text: '像日常聊天一样温和提醒');
  final _banned = TextEditingController(text: '你怎么又忘了');

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    for (final controller in [
      _message,
      _reminder,
      _schedule,
      _knowledgeTitle,
      _knowledgeContent,
      _callingName,
      _greetings,
      _sentenceStyle,
      _comfortStyle,
      _reminderStyle,
      _banned,
    ]) {
      controller.dispose();
    }
    super.dispose();
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
      final members = await api.familyMembers(familyId);
      final elders =
          members.where((member) => member['role'] == 'elder').toList();
      _elderId = elders.isEmpty ? null : elders.first['user_id'] as String?;
      final results = await Future.wait([
        api.knowledge(familyId),
        api.sentMessages(),
        api.voiceProfiles(),
      ]);
      _knowledge = results[0];
      _sent = results[1];
      _voiceProfiles = results[2];
    } catch (error) {
      _error = error.toString();
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _run(Future<void> Function() action, String success) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(success)));
      await _load();
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _sendMessage() async {
    if (_elderId == null || _message.text.trim().isEmpty) return;
    await _run(() async {
      await ref.read(apiClientProvider).sendFamilyMessage(
            recipientUserId: _elderId!,
            content: _message.text.trim(),
          );
      _message.clear();
    }, '留言已发送');
  }

  Future<void> _sendVoiceMessage() async {
    if (_elderId == null) return;
    final selected = await FilePicker.platform.pickFiles(
      type: FileType.audio,
      withData: true,
    );
    if (selected == null || selected.files.isEmpty) return;
    final file = selected.files.single;
    final bytes = file.bytes;
    if (bytes == null) {
      setState(() => _error = '无法读取所选音频，请选择 10MB 以内的音频文件');
      return;
    }
    await _run(() async {
      final api = ref.read(apiClientProvider);
      final media = await api.uploadAudio(bytes: bytes, filename: file.name);
      await api.sendFamilyMessage(
        recipientUserId: _elderId!,
        content: '一条家人语音留言',
        type: 'audio',
        audioObjectKey: media['id'] as String,
      );
    }, '语音留言已加密上传并发送');
  }

  Future<void> _createReminder() async {
    if (_elderId == null || _reminder.text.trim().isEmpty) return;
    await _run(() async {
      await ref.read(apiClientProvider).createReminder(
            ownerUserId: _elderId!,
            content: _reminder.text.trim(),
            scheduleRule: _schedule.text.trim(),
            category: 'family',
          );
      _reminder.clear();
    }, '提醒已创建');
  }

  Future<void> _addKnowledge() async {
    final familyId = ref.read(sessionProvider).familyId;
    if (familyId == null ||
        _knowledgeTitle.text.trim().isEmpty ||
        _knowledgeContent.text.trim().isEmpty) {
      return;
    }
    await _run(() async {
      await ref.read(apiClientProvider).createKnowledge(
            familyId: familyId,
            title: _knowledgeTitle.text.trim(),
            content: _knowledgeContent.text.trim(),
          );
      _knowledgeTitle.clear();
      _knowledgeContent.clear();
    }, '家庭资料已加入 RAG 知识库');
  }

  Future<void> _saveStyle() async {
    final familyId = ref.read(sessionProvider).familyId;
    if (familyId == null || _elderId == null) return;
    List<String> split(TextEditingController controller) => controller.text
        .split(RegExp(r'[，,;；\n]'))
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toList();
    await _run(() async {
      await ref.read(apiClientProvider).saveStyleProfile(
            familyId: familyId,
            targetUserId: _elderId!,
            callingName: _callingName.text.trim(),
            greetings: split(_greetings),
            sentenceStyle: _sentenceStyle.text.trim(),
            comfortStyle: _comfortStyle.text.trim(),
            reminderStyle: _reminderStyle.text.trim(),
            bannedPhrases: split(_banned),
          );
    }, '表达风格已保存，AI 仍会明确标识身份');
  }

  Future<void> _createVoiceDemo() async {
    final session = ref.read(sessionProvider);
    if (_elderId == null ||
        session.familyId == null ||
        session.userId == null) {
      return;
    }
    await _run(() async {
      final consent = await ref.read(apiClientProvider).createConsent(
        subjectUserId: session.userId!,
        familyId: session.familyId!,
        granteeUserId: _elderId,
        consentType: 'voice_use',
        scope: {
          'provider': 'neutral-device-tts',
          'ai_identity_notice': true,
          'clone_enabled': false,
        },
      );
      await ref.read(apiClientProvider).createVoiceEnrollment(
        consentId: consent['id'] as String,
        allowedRecipientIds: [_elderId!],
      );
    }, '声线授权演示已创建；当前使用中性设备声线，不克隆真人声音');
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 4,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('家庭协同工具'),
          bottom: const TabBar(
            isScrollable: true,
            tabs: [
              Tab(text: '留言'),
              Tab(text: '提醒'),
              Tab(text: '知识库'),
              Tab(text: '表达与声线'),
            ],
          ),
        ),
        body: _loading
            ? const Center(child: CircularProgressIndicator())
            : Column(
                children: [
                  if (_elderId == null)
                    const MaterialBanner(
                      content: Text('请先邀请老人加入家庭'),
                      actions: [SizedBox.shrink()],
                    ),
                  if (_error != null)
                    MaterialBanner(
                      content: Text(_error!),
                      actions: [
                        TextButton(onPressed: _load, child: const Text('重试'))
                      ],
                    ),
                  if (_busy) const LinearProgressIndicator(),
                  Expanded(
                    child: TabBarView(
                      children: [
                        _messageTab(),
                        _reminderTab(),
                        _knowledgeTab(),
                        _styleTab(),
                      ],
                    ),
                  ),
                ],
              ),
      ),
    );
  }

  Widget _messageTab() => ListView(
        padding: const EdgeInsets.all(18),
        children: [
          TextField(
            controller: _message,
            minLines: 3,
            maxLines: 6,
            decoration: const InputDecoration(
              labelText: '给老人留言',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: _busy ? null : _sendMessage,
            icon: const Icon(Icons.send),
            label: const Text('发送留言'),
          ),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: _busy ? null : _sendVoiceMessage,
            icon: const Icon(Icons.mic),
            label: const Text('选择并发送语音留言'),
          ),
          const SizedBox(height: 22),
          const Text('最近已发送', style: TextStyle(fontWeight: FontWeight.bold)),
          if (_sent.isEmpty) const Text('暂无留言'),
          ..._sent.take(20).map(
                (item) => ListTile(
                  leading: Icon(item['played_at'] == null
                      ? Icons.mark_email_unread
                      : Icons.done_all),
                  title: Text(item['content']?.toString() ?? ''),
                  subtitle:
                      Text(item['played_at'] == null ? '等待老人收听/查看' : '老人已查看'),
                ),
              ),
        ],
      );

  Widget _reminderTab() => ListView(
        padding: const EdgeInsets.all(18),
        children: [
          const Text('需要老人先授予“家人为我创建提醒”权限。'),
          const SizedBox(height: 12),
          TextField(
            controller: _reminder,
            decoration: const InputDecoration(
              labelText: '提醒内容',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _schedule,
            decoration: const InputDecoration(
              labelText: '时间规则，例如“每天 08:00”',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: _busy ? null : _createReminder,
            icon: const Icon(Icons.alarm_add),
            label: const Text('创建提醒'),
          ),
        ],
      );

  Widget _knowledgeTab() => ListView(
        padding: const EdgeInsets.all(18),
        children: [
          const Text('资料会被自动分块，仅在家庭权限范围内参与 RAG 检索。'),
          const SizedBox(height: 12),
          TextField(
            controller: _knowledgeTitle,
            decoration: const InputDecoration(
                labelText: '资料标题', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _knowledgeContent,
            minLines: 4,
            maxLines: 10,
            decoration: const InputDecoration(
                labelText: '资料内容', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 12),
          FilledButton(
              onPressed: _busy ? null : _addKnowledge,
              child: const Text('加入知识库')),
          const SizedBox(height: 20),
          ..._knowledge.map(
            (item) => Card(
              child: ListTile(
                title: Text(item['title']?.toString() ?? ''),
                subtitle: Text(
                  item['content']?.toString() ?? '',
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                ),
                trailing: IconButton(
                  tooltip: '删除',
                  onPressed: () => _run(
                    () => ref
                        .read(apiClientProvider)
                        .deleteKnowledge(item['id'] as String),
                    '资料已删除',
                  ),
                  icon: const Icon(Icons.delete_outline),
                ),
              ),
            ),
          ),
        ],
      );

  Widget _styleTab() => ListView(
        padding: const EdgeInsets.all(18),
        children: [
          const Text('风格只影响措辞，不能覆盖安全规则，也不会让 AI 冒充真实子女。'),
          const SizedBox(height: 12),
          for (final item in [
            (_callingName, '对老人的称呼'),
            (_greetings, '常用问候（逗号分隔）'),
            (_sentenceStyle, '句子风格'),
            (_comfortStyle, '安慰方式'),
            (_reminderStyle, '提醒方式'),
            (_banned, '禁用话术（逗号分隔）'),
          ]) ...[
            TextField(
              controller: item.$1,
              decoration: InputDecoration(
                  labelText: item.$2, border: const OutlineInputBorder()),
            ),
            const SizedBox(height: 12),
          ],
          FilledButton(
              onPressed: _busy ? null : _saveStyle,
              child: const Text('保存表达风格')),
          const Divider(height: 36),
          const Text('声线功能', style: TextStyle(fontWeight: FontWeight.bold)),
          const Text('本地版本使用中性设备 TTS。以下流程用于验证本人授权、接收对象和撤回机制。'),
          const SizedBox(height: 12),
          FilledButton.tonal(
            onPressed: _busy ? null : _createVoiceDemo,
            child: const Text('创建声线授权演示'),
          ),
          ..._voiceProfiles.map(
            (item) => ListTile(
              leading: const Icon(Icons.record_voice_over),
              title: Text(item['provider']?.toString() ?? '声线'),
              subtitle: Text('状态：${item['status']}'),
            ),
          ),
        ],
      );
}
