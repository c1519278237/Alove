import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/session.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _phone = TextEditingController();
  final _name = TextEditingController();
  final _code = TextEditingController();
  bool _codeRequested = false;

  @override
  void dispose() {
    _phone.dispose();
    _name.dispose();
    _code.dispose();
    super.dispose();
  }

  Future<void> _requestCode() async {
    final debugCode =
        await ref.read(sessionProvider.notifier).requestSms(_phone.text);
    if (!mounted) return;
    setState(() {
      _codeRequested = true;
      if (debugCode != null) _code.text = debugCode;
    });
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(debugCode == null ? '验证码已发送' : '本地开发验证码已自动填入'),
      ),
    );
  }

  Future<void> _login() async {
    await ref.read(sessionProvider.notifier).login(
          phone: _phone.text,
          code: _code.text,
          displayName: _name.text,
        );
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(28),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('归音', style: Theme.of(context).textTheme.displaySmall),
                  const SizedBox(height: 8),
                  const Text('让真实家人更及时地出现', style: TextStyle(fontSize: 20)),
                  const SizedBox(height: 32),
                  const _AiNotice(),
                  const SizedBox(height: 24),
                  TextField(
                    controller: _phone,
                    keyboardType: TextInputType.phone,
                    decoration: const InputDecoration(
                      labelText: '手机号',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: _name,
                    decoration: const InputDecoration(
                      labelText: '怎么称呼您',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  if (_codeRequested) ...[
                    const SizedBox(height: 16),
                    TextField(
                      controller: _code,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(
                        labelText: '6位验证码',
                        border: OutlineInputBorder(),
                      ),
                    ),
                  ],
                  if (session.error != null) ...[
                    const SizedBox(height: 12),
                    Text(session.error!,
                        style: const TextStyle(color: Colors.red)),
                  ],
                  const SizedBox(height: 24),
                  FilledButton(
                    onPressed: session.loading
                        ? null
                        : (_codeRequested ? _login : _requestCode),
                    child: Text(_codeRequested ? '登录' : '获取验证码'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _AiNotice extends StatelessWidget {
  const _AiNotice();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0xFFE6F3F1),
        borderRadius: BorderRadius.circular(16),
      ),
      child: const Padding(
        padding: EdgeInsets.all(18),
        child: Text('归音是 AI 助手，不是真实家人，也不能代替医生或紧急服务。'),
      ),
    );
  }
}
