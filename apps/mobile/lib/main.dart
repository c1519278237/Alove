import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'core/session.dart';
import 'core/notification_service.dart';
import 'features/auth/family_setup_screen.dart';
import 'features/auth/login_screen.dart';
import 'features/admin/admin_dashboard_screen.dart';
import 'features/care/care_need_screen.dart';
import 'features/calls/quick_call_screen.dart';
import 'features/conversation/conversation_screen.dart';
import 'features/family/family_tools_screen.dart';
import 'features/family/family_invite_screen.dart';
import 'features/home/child_home_screen.dart';
import 'features/home/elder_home_screen.dart';
import 'features/privacy/elder_manage_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await NotificationService.instance.initialize();
  runApp(const ProviderScope(child: GuiyinApp()));
}

// Keep one router instance for the lifetime of the application. Recreating the
// router whenever SessionState changes also recreates the active login route,
// which used to clear the SMS-code state as soon as a request started.
final _routerProvider = Provider<GoRouter>((ref) {
  final router = GoRouter(
    initialLocation: '/loading',
    redirect: (context, state) {
      final session = ref.read(sessionProvider);
      // Authentication actions also use `loading`. Keep the login route alive
      // while requesting/verifying an SMS code so its form state is preserved.
      // The dedicated loading route is only needed during app restoration.
      if (session.loading) {
        return state.matchedLocation == '/login' ? null : '/loading';
      }
      if (!session.isAuthenticated) return '/login';
      if (!session.hasFamily) return '/family-setup';
      if (state.matchedLocation == '/login' ||
          state.matchedLocation == '/loading' ||
          state.matchedLocation == '/family-setup') {
        return session.isElder ? '/elder' : '/child';
      }
      return null;
    },
    routes: [
      GoRoute(
        path: '/loading',
        builder: (context, state) => const _LoadingScreen(),
      ),
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginScreen(),
      ),
      GoRoute(
        path: '/family-setup',
        builder: (context, state) => const FamilySetupScreen(),
      ),
      GoRoute(
        path: '/elder',
        builder: (context, state) => const ElderHomeScreen(),
      ),
      GoRoute(
        path: '/child',
        builder: (context, state) => const ChildHomeScreen(),
      ),
      GoRoute(
        path: '/conversation',
        builder: (context, state) => const ConversationScreen(),
      ),
      GoRoute(
        path: '/elder-manage',
        builder: (context, state) => const ElderManageScreen(),
      ),
      GoRoute(
        path: '/care-need',
        builder: (context, state) => const CareNeedScreen(),
      ),
      GoRoute(
        path: '/quick-call',
        builder: (context, state) => const QuickCallScreen(),
      ),
      GoRoute(
        path: '/family-tools',
        builder: (context, state) => const FamilyToolsScreen(),
      ),
      GoRoute(
        path: '/family-invite',
        builder: (context, state) => const FamilyInviteScreen(),
      ),
      GoRoute(
        path: '/admin',
        builder: (context, state) => const AdminDashboardScreen(),
      ),
    ],
  );

  ref.listen<SessionState>(sessionProvider, (previous, next) {
    router.refresh();
  });
  ref.onDispose(router.dispose);
  return router;
});

class GuiyinApp extends ConsumerWidget {
  const GuiyinApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(_routerProvider);

    return MaterialApp.router(
      title: '归音 AI 家庭关怀',
      debugShowCheckedModeBanner: false,
      routerConfig: router,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF1C8585),
          primary: const Color(0xFF176B7A),
          secondary: const Color(0xFFE9A23B),
          surface: const Color(0xFFF7FAFA),
        ),
        scaffoldBackgroundColor: const Color(0xFFF7FAFA),
        useMaterial3: true,
        textTheme: const TextTheme(
          bodyLarge: TextStyle(fontSize: 20, height: 1.5),
          bodyMedium: TextStyle(fontSize: 17, height: 1.5),
          titleLarge: TextStyle(fontSize: 26, fontWeight: FontWeight.w700),
        ),
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            minimumSize: const Size.fromHeight(56),
            textStyle:
                const TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
          ),
        ),
      ),
    );
  }
}

class _LoadingScreen extends StatelessWidget {
  const _LoadingScreen();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(body: Center(child: CircularProgressIndicator()));
  }
}
