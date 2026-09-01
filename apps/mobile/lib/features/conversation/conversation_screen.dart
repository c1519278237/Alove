import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';

import '../../core/session.dart';

class ConversationScreen extends ConsumerStatefulWidget {
  const ConversationScreen({super.key});

  @override
  ConsumerState<ConversationScreen> createState() => _ConversationScreenState();
}

class _ChatBubble {
  const _ChatBubble(
    this.text, {
    required this.fromUser,
    this.safetyNotice,
    this.sources = const [],
    this.imageBytes,
  });

  final String text;
  final bool fromUser;
  final String? safetyNotice;
  final List<Map<String, dynamic>> sources;
  final Uint8List? imageBytes;
}

class _PendingImage {
  const _PendingImage({required this.name, required this.bytes});

  final String name;
  final Uint8List bytes;
}

class _ConversationScreenState extends ConsumerState<ConversationScreen> {
  final _input = TextEditingController();
  final _speech = SpeechToText();
  final _tts = FlutterTts();
  final _messages = <_ChatBubble>[];
  String? _conversationId;
  bool _busy = true;
  bool _listening = false;
  bool _shareSummary = false;
  String? _error;
  _PendingImage? _pendingImage;

  @override
  void initState() {
    super.initState();
    _startConversation();
    _tts.setLanguage('zh-CN');
    _tts.setSpeechRate(0.45);
  }

  @override
  void dispose() {
    _input.dispose();
    _speech.stop();
    _tts.stop();
    super.dispose();
  }

  Future<void> _startConversation() async {
    try {
      final familyId = ref.read(sessionProvider).familyId!;
      final result =
          await ref.read(apiClientProvider).createConversation(familyId);
      setState(() {
        _conversationId = result['id'] as String;
        _busy = false;
        _messages.add(
          const _ChatBubble(
            '我是归音 AI 助手，不是真实家人。您想聊聊天，还是需要我帮您整理一件事？',
            fromUser: false,
          ),
        );
      });
    } catch (error) {
      setState(() {
        _busy = false;
        _error = error.toString();
      });
    }
  }

  Future<void> _toggleListening() async {
    if (_listening) {
      await _speech.stop();
      setState(() => _listening = false);
      if (_input.text.trim().isNotEmpty) await _send();
      return;
    }
    final available = await _speech.initialize();
    if (!available) {
      setState(() => _error = '手机语音识别不可用，请使用文字输入。');
      return;
    }
    setState(() {
      _listening = true;
      _error = null;
    });
    await _speech.listen(
      onResult: (SpeechRecognitionResult result) {
        setState(() => _input.text = result.recognizedWords);
      },
      listenOptions: SpeechListenOptions(
        localeId: 'zh_CN',
        listenMode: ListenMode.dictation,
        partialResults: true,
        cancelOnError: true,
      ),
    );
  }

  Future<void> _send() async {
    final pendingImage = _pendingImage;
    final typedText = _input.text.trim();
    if ((typedText.isEmpty && pendingImage == null) ||
        _conversationId == null ||
        _busy) {
      return;
    }
    final text = typedText.isEmpty ? '请帮我看看这张图片' : typedText;
    setState(() {
      _messages.add(
        _ChatBubble(
          text,
          fromUser: true,
          imageBytes: pendingImage?.bytes,
        ),
      );
      _input.clear();
      _pendingImage = null;
      _busy = true;
      _error = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      String? imageMediaId;
      if (pendingImage != null) {
        final media = await api.uploadImage(
          bytes: pendingImage.bytes,
          filename: pendingImage.name,
        );
        imageMediaId = media['id'] as String;
      }
      final result = await api.sendMessage(
        _conversationId!,
        text,
        imageMediaId: imageMediaId,
      );
      final assistant = result['assistant_message'] as Map<String, dynamic>;
      final responseText = assistant['text'] as String;
      final sources = (result['evidence'] as List<dynamic>? ?? const [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList();
      setState(
        () => _messages.add(
          _ChatBubble(
            responseText,
            fromUser: false,
            safetyNotice: result['safety_notice'] as String?,
            sources: sources,
          ),
        ),
      );
      await _tts.speak(responseText);
    } catch (error) {
      setState(() {
        _error = error.toString();
        _pendingImage ??= pendingImage;
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _pickImage() async {
    final accepted = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('使用AI查看图片'),
        content: const Text(
          '图片会加密保存在本机服务，并发送给当前配置的AI模型分析。请勿上传身份证、银行卡、验证码或其他不必要的敏感信息。AI识图可能出错，不能据此诊断疾病或决定用药。',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('选择图片'),
          ),
        ],
      ),
    );
    if (accepted != true || !mounted) return;
    final selected = await FilePicker.platform.pickFiles(
      type: FileType.image,
      withData: true,
    );
    if (selected == null || selected.files.isEmpty || !mounted) return;
    final file = selected.files.single;
    final bytes = file.bytes;
    if (bytes == null) {
      setState(() => _error = '无法读取所选图片，请重新选择');
      return;
    }
    if (bytes.length > 5 * 1024 * 1024) {
      setState(() => _error = '图片不能超过5MB');
      return;
    }
    setState(() {
      _pendingImage = _PendingImage(name: file.name, bytes: bytes);
      _error = null;
    });
  }

  Future<void> _endConversation() async {
    if (_conversationId == null) {
      if (mounted) Navigator.of(context).pop();
      return;
    }
    setState(() => _busy = true);
    try {
      await ref.read(apiClientProvider).endConversation(_conversationId!);
      if (mounted) Navigator.of(context).pop();
    } catch (error) {
      if (mounted) {
        setState(() {
          _busy = false;
          _error = error.toString();
        });
      }
    }
  }

  Future<void> _setSharing(bool value) async {
    if (_conversationId == null) return;
    try {
      await ref.read(apiClientProvider).setConversationSharing(
            _conversationId!,
            value ? 'family_summary' : 'private',
          );
      setState(() => _shareSummary = value);
    } catch (error) {
      setState(() => _error = error.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('和归音对话'),
        actions: [
          TextButton.icon(
            onPressed: _busy ? null : _endConversation,
            icon: const Icon(Icons.check_circle_outline),
            label: const Text('结束'),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            Container(
              width: double.infinity,
              color: const Color(0xFFE6F3F1),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              child: const Text(
                '当前正在与 AI 助手对话 · 重要事情请联系真实家人',
                textAlign: TextAlign.center,
              ),
            ),
            SwitchListTile(
              title: const Text('允许本次对话用于家庭关怀摘要'),
              subtitle: const Text('只生成主题和需求摘要，不向家人展示完整对话'),
              value: _shareSummary,
              onChanged: _conversationId == null ? null : _setSharing,
            ),
            Expanded(
              child: ListView.builder(
                padding: const EdgeInsets.all(16),
                itemCount: _messages.length,
                itemBuilder: (context, index) {
                  final message = _messages[index];
                  return Align(
                    alignment: message.fromUser
                        ? Alignment.centerRight
                        : Alignment.centerLeft,
                    child: Container(
                      constraints: const BoxConstraints(maxWidth: 520),
                      margin: const EdgeInsets.only(bottom: 12),
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: message.fromUser
                            ? const Color(0xFFDCEAF5)
                            : Colors.white,
                        borderRadius: BorderRadius.circular(18),
                        border: Border.all(color: const Color(0xFFD5E0E3)),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (message.imageBytes != null) ...[
                            ClipRRect(
                              borderRadius: BorderRadius.circular(12),
                              child: Image.memory(
                                message.imageBytes!,
                                width: 220,
                                height: 160,
                                fit: BoxFit.cover,
                              ),
                            ),
                            const SizedBox(height: 10),
                          ],
                          Text(
                            message.text,
                            style: const TextStyle(fontSize: 20),
                          ),
                          if (message.safetyNotice != null) ...[
                            const SizedBox(height: 10),
                            Text(
                              message.safetyNotice!,
                              style: TextStyle(
                                color: Theme.of(context).colorScheme.error,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ],
                          if (message.sources.isNotEmpty) ...[
                            const Divider(height: 24),
                            Text(
                              '参考了 ${message.sources.length} 条已授权家庭资料',
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                            for (final source in message.sources.take(3))
                              Text(
                                '• ${source['title'] ?? source['source_type'] ?? '家庭资料'}',
                                style: Theme.of(context).textTheme.bodySmall,
                              ),
                          ],
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Text(_error!, style: const TextStyle(color: Colors.red)),
              ),
            if (_busy) const LinearProgressIndicator(),
            if (_pendingImage != null)
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 8, 14, 0),
                child: Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: const Color(0xFFE6F3F1),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Row(
                    children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: Image.memory(
                          _pendingImage!.bytes,
                          width: 64,
                          height: 64,
                          fit: BoxFit.cover,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          _pendingImage!.name,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      IconButton(
                        tooltip: '移除图片',
                        onPressed: _busy
                            ? null
                            : () => setState(() => _pendingImage = null),
                        icon: const Icon(Icons.close),
                      ),
                    ],
                  ),
                ),
              ),
            Padding(
              padding: const EdgeInsets.all(14),
              child: Row(
                children: [
                  IconButton.filled(
                    onPressed: _busy ? null : _toggleListening,
                    tooltip: _listening ? '结束说话' : '按下说话',
                    iconSize: 34,
                    icon: Icon(_listening ? Icons.stop : Icons.mic),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filledTonal(
                    onPressed: _busy ? null : _pickImage,
                    tooltip: '选择图片让AI看看',
                    iconSize: 30,
                    icon: const Icon(Icons.add_photo_alternate_outlined),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: TextField(
                      controller: _input,
                      minLines: 1,
                      maxLines: 3,
                      style: const TextStyle(fontSize: 19),
                      decoration: const InputDecoration(
                        hintText: '也可以在这里打字',
                        border: OutlineInputBorder(),
                      ),
                      onSubmitted: (_) => _send(),
                    ),
                  ),
                  const SizedBox(width: 10),
                  IconButton.filledTonal(
                    onPressed: _busy ? null : _send,
                    tooltip: '发送',
                    iconSize: 32,
                    icon: const Icon(Icons.send),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
