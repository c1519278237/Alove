import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'session.dart';

enum ChildSection { home, invite, tools, admin }

class ChildNavigationBar extends ConsumerWidget {
  const ChildNavigationBar({required this.current, super.key});

  final ChildSection current;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isAdmin =
        ref.watch(sessionProvider.select((state) => state.role == 'admin'));
    final entries = <(ChildSection, String, IconData, String)>[
      (ChildSection.home, '关怀首页', Icons.home_outlined, '/child'),
      (ChildSection.invite, '邀请家人', Icons.person_add_alt_1, '/family-invite'),
      (
        ChildSection.tools,
        '家庭工具',
        Icons.dashboard_customize_outlined,
        '/family-tools'
      ),
      if (isAdmin)
        (ChildSection.admin, '安全面板', Icons.security_outlined, '/admin'),
    ];
    final selectedIndex = entries.indexWhere((entry) => entry.$1 == current);

    return NavigationBar(
      selectedIndex: selectedIndex < 0 ? 0 : selectedIndex,
      onDestinationSelected: (index) {
        final target = entries[index];
        if (target.$1 != current) context.go(target.$4);
      },
      destinations: [
        for (final entry in entries)
          NavigationDestination(icon: Icon(entry.$3), label: entry.$2),
      ],
    );
  }
}
