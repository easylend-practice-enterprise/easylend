import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../scan_aztec_screen.dart';
import '../modals/inactivity_modal.dart';

class ScreenSwitcher extends ConsumerStatefulWidget {
  const ScreenSwitcher({super.key});

  @override
  ConsumerState<ScreenSwitcher> createState() => _ScreenSwitcherState();
}

class _ScreenSwitcherState extends ConsumerState<ScreenSwitcher> {
  void _openScanAztec() {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const ScanAztecScreen()),
    );
  }

  void _showInactivityModal() {
    showDialog(
      context: context,
      builder: (_) => InactivityModal(
        onStay: () => Navigator.of(context).pop(),
        onLogout: () {
          Navigator.of(context).pop();
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            Icon(Icons.bug_report, color: Colors.orange[700], size: 20),
            const SizedBox(width: 8),
            const Text('Debug Mode'),
            const Spacer(),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: Colors.red,
                borderRadius: BorderRadius.circular(4),
              ),
              child: const Text(
                'DEBUG',
                style: TextStyle(color: Colors.white, fontSize: 10),
              ),
            ),
          ],
        ),
        backgroundColor: Colors.grey[900],
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              FloatingActionButton.large(
                onPressed: _openScanAztec,
                backgroundColor: Colors.cyan,
                child: const Icon(Icons.qr_code_scanner, size: 48),
              ),
              const SizedBox(height: 16),
              const Text(
                'Scan Aztec Code',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
              const SizedBox(height: 24),
              OutlinedButton.icon(
                onPressed: _showInactivityModal,
                icon: const Icon(Icons.timer_off),
                label: const Text('Show Inactivity Modal'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.orange,
                  side: const BorderSide(color: Colors.orange),
                ),
              ),
              if (!kDebugMode) ...[
                const SizedBox(height: 8),
                Text(
                  'Debug mode is disabled. Set DebugConfig.debugEnabled = true to activate.',
                  style: TextStyle(
                    color: Colors.grey[600],
                    fontSize: 12,
                  ),
                  textAlign: TextAlign.center,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
