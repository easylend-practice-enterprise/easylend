import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../theme.dart';

class LendingCompleteScreen extends ConsumerStatefulWidget {
  final String? loanId;

  const LendingCompleteScreen({super.key, this.loanId});

  @override
  ConsumerState<LendingCompleteScreen> createState() => _LendingCompleteScreenState();
}

class _LendingCompleteScreenState extends ConsumerState<LendingCompleteScreen> {
  // 5 hour grace period - for demo using 5 minutes
  late Duration _remainingTime;
  late Duration _totalTime;
  Timer? _timer;
  bool _isExpired = false;

  @override
  void initState() {
    super.initState();
    _totalTime = const Duration(hours: 5);
    _remainingTime = _totalTime;
    _startTimer();
  }

  void _startTimer() {
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      setState(() {
        if (_remainingTime.inSeconds > 0) {
          _remainingTime = _remainingTime - const Duration(seconds: 1);
        } else {
          _isExpired = true;
          _timer?.cancel();
        }
      });
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  String _pad(int n) => n.toString().padLeft(2, '0');

  void _onReportDamage() {
    // Damage report flow pending implementation
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text('Report Damage'),
        content: const Text('Damage reporting is not yet implemented.'),
        actions: [
          ElevatedButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

  void _onDone() {
    context.go('/catalog');
  }

  @override
  Widget build(BuildContext context) {
    final hours = _pad(_remainingTime.inHours);
    final minutes = _pad(_remainingTime.inMinutes.remainder(60));
    final seconds = _pad(_remainingTime.inSeconds.remainder(60));

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        centerTitle: true,
        title: const Text('Lending Complete'),
        actions: [
          TextButton(
            onPressed: _onDone,
            child: const Text('Done'),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            const SizedBox(height: 24),
            Icon(
              _isExpired ? Icons.warning : Icons.check_circle,
              size: 96,
              color: _isExpired ? Colors.orange : AppColors.accent,
            ),
            const SizedBox(height: 12),
            Text(
              _isExpired ? 'Grace Period Expired' : 'Item Lent Successfully',
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Text(
                _isExpired
                    ? 'Please return your item immediately.'
                    : 'Your item has been lent out securely. The grace period has started.',
                textAlign: TextAlign.center,
              ),
            ),
            const SizedBox(height: 24),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24.0),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    _TimeBox(value: hours, label: 'Hours'),
                    const SizedBox(height: 12),
                    _TimeBox(value: minutes, label: 'Minutes'),
                    const SizedBox(height: 12),
                    _TimeBox(value: seconds, label: 'Seconds'),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(16.0),
              child: OutlinedButton.icon(
                onPressed: _onReportDamage,
                icon: const Icon(Icons.report_problem),
                label: const Text('Report Pre-existing Damage'),
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size.fromHeight(48),
                  foregroundColor: AppColors.text,
                  side: BorderSide(color: AppColors.divider),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TimeBox extends StatelessWidget {
  final String value;
  final String label;

  const _TimeBox({required this.value, required this.label});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          height: 64,
          width: double.infinity,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppColors.divider),
          ),
          child: Center(
            child: Text(
              value,
              style: TextStyle(
                fontSize: 28,
                fontWeight: FontWeight.bold,
                color: AppColors.text,
              ),
            ),
          ),
        ),
        const SizedBox(height: 6),
        Text(label, style: TextStyle(fontSize: 12, color: AppColors.text)),
      ],
    );
  }
}
