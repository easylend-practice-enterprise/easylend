import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'app.dart';
import 'providers/providers.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  runApp(
    ProviderScope(
      child: _IdleTimerWrapper(
        onIdle: () {},
        child: const App(),
      ),
    ),
  );
}

class _IdleTimerWrapper extends ConsumerStatefulWidget {
  final Widget child;
  final VoidCallback onIdle;

  const _IdleTimerWrapper({required this.child, required this.onIdle});

  @override
  ConsumerState<_IdleTimerWrapper> createState() => _IdleTimerWrapperState();
}

class _IdleTimerWrapperState extends ConsumerState<_IdleTimerWrapper> {
  Timer? _idleTimer;
  static const _idleDuration = Duration(seconds: 60);

  @override
  void initState() {
    super.initState();
    _resetTimer();
  }

  void _resetTimer() {
    _idleTimer?.cancel();
    _idleTimer = Timer(_idleDuration, _handleIdle);
  }

  void _handleIdle() {
    ref.read(authProvider.notifier).logout();
    context.go('/login');
  }

  @override
  void dispose() {
    _idleTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Listener(
      onPointerDown: (_) => _resetTimer(),
      child: widget.child,
    );
  }
}
