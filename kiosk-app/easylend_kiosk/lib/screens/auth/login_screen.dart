import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../providers/providers.dart';
import '../../services/api/api_service.dart';
import '../../theme.dart';

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
  bool _isValidatingNfc = false;
  String? _error;
  bool _isCheckingConnection = false;

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

  Future<void> _onNfcDetected(String nfcTagId) async {
    final tag = nfcTagId.trim();
    if (tag.isEmpty || !mounted || _isValidatingNfc) {
      return;
    }

    setState(() {
      _isNfcScanning = false;
      _isValidatingNfc = true;
      _error = null;
    });

    final isValid = await ref.read(authProvider.notifier).nfcLogin(tag);

    if (!mounted) {
      return;
    }

    setState(() {
      _isValidatingNfc = false;
    });

    if (!isValid) {
      final authState = ref.read(authProvider);
      if (!mounted) {
        return;
      }
      setState(() {
        _error = authState.error ?? 'Invalid NFC badge. Please try again.';
        _isNfcScanning = true;
      });
      return;
    }

    // Navigate to PIN entry screen only after the backend validates the badge.
    context.go('/pin/${Uri.encodeComponent(tag)}');
  }

  void _submitManualNfcTag() {
    _showDebugLoginDialog();
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
                'Enter an NFC tag to validate before PIN login.',
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

      await _onNfcDetected(tag);
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

  Future<void> _checkBackendConnection() async {
    if (_isCheckingConnection) return;
    _isCheckingConnection = true;
    final messenger = ScaffoldMessenger.of(context);
    try {
      final client = ref.read(apiClientProvider);
      final elapsed = await client.ping();
      if (!mounted) return;
      messenger.showSnackBar(
        SnackBar(
          content: Text('Backend connected (${elapsed.inMilliseconds}ms)'),
          backgroundColor: Colors.green[700],
          duration: const Duration(seconds: 3),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      messenger.showSnackBar(
        SnackBar(
          content: Text('Backend unreachable: $e'),
          backgroundColor: Colors.red[700],
          duration: const Duration(seconds: 5),
        ),
      );
    } finally {
      _isCheckingConnection = false;
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
            onPressed: () async {
              final tag = controller.text.trim();
              if (tag.isEmpty) {
                return;
              }
              Navigator.pop(context);
              await _onNfcDetected(tag);
            },
            child: const Text('Submit'),
          ),
        ],
      ),
    ).then((_) => controller.dispose());
  }

  @override
  Widget build(BuildContext context) {
    final titleText = _isValidatingNfc
        ? 'Validating Badge...'
        : _isNfcScanning
        ? 'Waiting for Badge...'
        : 'Badge Scanning Paused';
    final subtitleText = _isValidatingNfc
        ? 'Checking the NFC badge with the backend...'
        : kDebugMode
        ? 'Hold your NFC badge near the back of your device.'
        : _isNfcScanning
        ? 'Hold your NFC badge near the back of your device.'
        : 'Tap NFC badge to continue.';

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
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Text(
                      'Asset Manager',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    if (kDebugMode) ...[
                      const SizedBox(width: 12),
                      Tooltip(
                        message: 'Check backend connection',
                        child: IconButton(
                          icon: const Icon(
                            Icons.wifi_tethering,
                            color: Colors.green,
                            size: 20,
                          ),
                          onPressed: _checkBackendConnection,
                          padding: EdgeInsets.zero,
                          constraints: const BoxConstraints(),
                        ),
                      ),
                    ],
                  ],
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
                      titleText,
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 28,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      subtitleText,
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
                  onPressed: kDebugMode ? _submitManualNfcTag : _onManualLogin,
                  style: TextButton.styleFrom(
                    backgroundColor: kDebugMode ? Colors.orange : Colors.white,
                    foregroundColor: Colors.black,
                    minimumSize: const Size.fromHeight(48),
                  ),
                  child: Text(
                    kDebugMode ? 'Debug Login' : 'Login with Credentials',
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
