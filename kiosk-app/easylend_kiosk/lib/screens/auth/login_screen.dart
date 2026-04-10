import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

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
  }

  void _onNfcDetected(String nfcTagId) {
    if (!mounted) {
      return;
    }

    setState(() {
      _isNfcScanning = false;
    });

    if (!mounted) {
      return;
    }

    // Navigate to PIN entry screen
    context.go('/pin/${Uri.encodeComponent(nfcTagId)}');
  }

  void _submitManualNfcTag() {
    _showDebugLoginDialog();
  }

  Future<void> _navigateToPinSafely(String rawTag) async {
    final tag = rawTag.trim();
    if (tag.isEmpty || !mounted) {
      return;
    }

    try {
      setState(() {
        _error = null;
        _isNfcScanning = false;
      });
      context.go('/pin/${Uri.encodeComponent(tag)}');
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = 'Unable to continue to PIN. Please try again.';
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Navigation failed. Please retry debug login.'),
        ),
      );
    }
  }

  Future<void> _showDebugLoginDialog() async {
    if (!mounted) {
      return;
    }

    final navigator = Navigator.of(context, rootNavigator: true);
    String enteredTag = '';

    try {
      final tag = await showDialog<String>(
        context: context,
        barrierDismissible: true,
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
              const Text(
                'Enter an NFC tag to test backend PIN login.',
                style: TextStyle(color: Colors.grey, fontSize: 13),
              ),
              const SizedBox(height: 16),
              TextField(
                autofocus: true,
                decoration: const InputDecoration(
                  hintText: 'Enter NFC Tag ID',
                  border: OutlineInputBorder(),
                ),
                textInputAction: TextInputAction.done,
                onChanged: (value) {
                  enteredTag = value;
                },
                onSubmitted: (value) {
                  final submittedTag = value.trim();
                  if (submittedTag.isEmpty) {
                    return;
                  }
                  if (navigator.canPop()) {
                    navigator.pop(submittedTag);
                  }
                },
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () {
                if (navigator.canPop()) {
                  navigator.pop();
                }
              },
              child: const Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: () {
                final submittedTag = enteredTag.trim();
                if (submittedTag.isEmpty) {
                  return;
                }
                if (navigator.canPop()) {
                  navigator.pop(submittedTag);
                }
              },
              child: const Text('Continue'),
            ),
          ],
        ),
      );

      if (tag == null || tag.trim().isEmpty) {
        return;
      }

      await _navigateToPinSafely(tag);
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = 'Debug login failed. Please try again.';
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Debug login encountered an error.')),
      );
    }
  }

  void _onManualLogin() {
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
              final tag = controller.text.trim();
              if (tag.isEmpty) {
                return;
              }
              Navigator.pop(context);
              _onNfcDetected(tag);
            },
            child: const Text('Submit'),
          ),
        ],
      ),
    ).then((_) => controller.dispose());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        top: false,
        child: Stack(
          fit: StackFit.expand,
          children: [
            // Title at top
            Align(
              alignment: Alignment.topCenter,
              child: Padding(
                padding: const EdgeInsets.only(top: 32.0),
                child: const Text(
                  'Asset Manager',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ),
            // Logo badge
            Center(
              child: AnimatedBuilder(
                animation: _pulseAnimation,
                builder: (context, child) {
                  final glowOpacity = _isNfcScanning
                      ? (38 * _pulseAnimation.value).toInt()
                      : 0;
                  final glowBlur = _isNfcScanning
                      ? 40 * _pulseAnimation.value
                      : 0.0;
                  final glowSpread = _isNfcScanning
                      ? 10 * _pulseAnimation.value
                      : 0.0;

                  return Container(
                    width: 240,
                    height: 240,
                    decoration: BoxDecoration(
                      color: AppColors.background,
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: Colors.cyan.withAlpha(glowOpacity),
                          blurRadius: glowBlur,
                          spreadRadius: glowSpread,
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
            ),
            // Prompt and cancel button below logo
            Align(
              alignment: const Alignment(0, 0.4),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 32.0),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      _isNfcScanning
                          ? 'Waiting for Badge...'
                          : 'Badge Scanning Paused',
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 28,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      DebugConfig.isActive
                          ? 'Hold your NFC badge near the back of your device.'
                          : _isNfcScanning
                          ? 'Hold your NFC badge near the back of your device.'
                          : 'Tap NFC badge to continue.',
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Colors.grey),
                    ),
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
            // Login button at bottom
            Align(
              alignment: Alignment.bottomCenter,
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: TextButton(
                  onPressed: DebugConfig.isActive
                      ? _submitManualNfcTag
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
            ),
          ],
        ),
      ),
    );
  }
}
