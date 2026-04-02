import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../providers/providers.dart';
import '../../theme.dart';
import '../../config/debug_credentials.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;
  bool _isNfcScanning = false;
  String? _error;
  Timer? _nfcDetectionTimer;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..repeat(reverse: true);

    _pulseAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );

    // Start NFC listening when screen loads
    _startNfcListening();
  }

  @override
  void dispose() {
    _nfcDetectionTimer?.cancel();
    _pulseController.dispose();
    _isNfcScanning = false;
    super.dispose();
  }

  void _startNfcListening() {
    if (!mounted) {
      return;
    }

    setState(() {
      _isNfcScanning = true;
      _error = null;
    });

    _nfcDetectionTimer?.cancel();

    // NFC integration pending - using simulated detection for now
    _nfcDetectionTimer = Timer(const Duration(seconds: 2), () {
      if (!mounted || !_isNfcScanning) {
        return;
      }

      // Simulate detecting an NFC tag
      _onNfcDetected('NFC-TAG-12345');
    });
  }

  void _stopNfcListening() {
    _nfcDetectionTimer?.cancel();

    if (!mounted) {
      _isNfcScanning = false;
      return;
    }

    setState(() => _isNfcScanning = false);
    // NFC cleanup handled by framework when widget unmounts
  }

  void _onNfcDetected(String nfcTagId) {
    if (!mounted) {
      return;
    }

    _nfcDetectionTimer?.cancel();

    setState(() {
      _isNfcScanning = false;
    });

    if (!mounted) {
      return;
    }

    // Navigate to PIN entry screen
    context.go('/pin/$nfcTagId');
  }

  void _onManualLogin() {
    // For demo/testing: manually enter NFC tag
    _showManualNfcDialog();
  }

  void _showDebugLoginDialog() {
    final usernameController = TextEditingController();
    final passwordController = TextEditingController();
    // Capture the parent's context before showing dialog
    final parentRouter = GoRouter.of(context);
    final parentNavigator = Navigator.of(context);

    showDialog(
      context: context,
      builder: (dialogContext) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: Row(
          children: [
            Icon(Icons.bug_report, color: Colors.orange[700]),
            const SizedBox(width: 8),
            const Text('Debug Login'),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: usernameController,
              decoration: const InputDecoration(
                hintText: 'Username',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: passwordController,
              obscureText: true,
              decoration: const InputDecoration(
                hintText: 'Password',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.orange.withAlpha(25),
                borderRadius: BorderRadius.circular(4),
                border: Border.all(color: Colors.orange.withAlpha(76)),
              ),
              child: const Row(
                children: [
                  Icon(Icons.warning, color: Colors.orange, size: 16),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Debug mode only - credentials logged for testing',
                      style: TextStyle(color: Colors.orange, fontSize: 11),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () async {
              final username = usernameController.text;
              final password = passwordController.text;

              if (DebugConfig.isValidCredentials(username, password)) {
                parentNavigator.pop();
                final success = await ref
                    .read(authProvider.notifier)
                    .debugLogin(username, password);

                if (!mounted) {
                  return;
                }

                if (success) {
                  parentRouter.go('/catalog');
                }
              } else {
                ScaffoldMessenger.of(dialogContext).showSnackBar(
                  const SnackBar(
                    content: Text('Invalid credentials'),
                    backgroundColor: Colors.red,
                  ),
                );
              }
            },
            style: ElevatedButton.styleFrom(backgroundColor: Colors.orange),
            child: const Text('Login'),
          ),
        ],
      ),
    );
  }

  void _showManualNfcDialog() {
    final controller = TextEditingController();
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text('Manual NFC Entry'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(
            hintText: 'Enter NFC Tag ID',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () {
              if (controller.text.isNotEmpty) {
                Navigator.pop(context);
                _onNfcDetected(controller.text);
              }
            },
            child: const Text('Submit'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        child: Column(
          children: [
            const SizedBox(height: 24),
            const Center(
              child: Text(
                'Asset Manager',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
            const SizedBox(height: 24),
            Expanded(
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    AnimatedBuilder(
                      animation: _pulseAnimation,
                      builder: (context, child) {
                        return Container(
                          width: 240,
                          height: 240,
                          decoration: BoxDecoration(
                            color: AppColors.background,
                            shape: BoxShape.circle,
                            boxShadow: [
                              BoxShadow(
                                color: Colors.cyan.withAlpha(
                                  (38 * _pulseAnimation.value).toInt(),
                                ),
                                blurRadius: 40 * _pulseAnimation.value,
                                spreadRadius: 10 * _pulseAnimation.value,
                              ),
                            ],
                          ),
                          child: const Center(
                            child: Icon(
                              Icons.contactless,
                              size: 120,
                              color: Colors.cyan,
                            ),
                          ),
                        );
                      },
                    ),
                    const SizedBox(height: 24),
                    Text(
                      _isNfcScanning
                          ? 'Waiting for Badge...'
                          : 'Scan your Badge',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 28,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 32.0),
                      child: Text(
                        _isNfcScanning
                            ? 'Hold your NFC badge near the back of your device.'
                            : 'Tap NFC badge or use credentials below.',
                        textAlign: TextAlign.center,
                        style: const TextStyle(color: Colors.grey),
                      ),
                    ),
                    if (_isNfcScanning) ...[
                      const SizedBox(height: 16),
                      const CircularProgressIndicator(color: Colors.cyan),
                      const SizedBox(height: 16),
                      TextButton(
                        onPressed: _stopNfcListening,
                        child: const Text('Cancel'),
                      ),
                    ],
                    if (_error != null) ...[
                      const SizedBox(height: 16),
                      Text(
                        _error!,
                        style: const TextStyle(color: Colors.red),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(16.0),
              child: TextButton(
                onPressed: DebugConfig.isActive
                    ? _showDebugLoginDialog
                    : _onManualLogin,
                style: TextButton.styleFrom(
                  backgroundColor: DebugConfig.isActive
                      ? Colors.orange
                      : Colors.white,
                  foregroundColor: Colors.black,
                  minimumSize: const Size.fromHeight(48),
                ),
                child: Text(
                  DebugConfig.isActive
                      ? 'Debug Login'
                      : 'Login with Credentials',
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
