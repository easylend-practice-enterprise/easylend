import 'dart:async';
import 'package:flutter/material.dart';
import '../../theme.dart';

class InactivityModal extends StatefulWidget {
  final VoidCallback onStay;
  final VoidCallback onLogout;
  final int timeoutSeconds;

  const InactivityModal({
    super.key,
    required this.onStay,
    required this.onLogout,
    this.timeoutSeconds = 30,
  });

  @override
  State<InactivityModal> createState() => _InactivityModalState();
}

class _InactivityModalState extends State<InactivityModal> {
  late int _secondsRemaining;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _secondsRemaining = widget.timeoutSeconds;
    _startTimer();
  }

  void _startTimer() {
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      setState(() {
        if (_secondsRemaining > 0) {
          _secondsRemaining--;
        } else {
          _timer?.cancel();
          widget.onLogout();
        }
      });
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  String get _paddedSeconds => _secondsRemaining.toString().padLeft(2, '0');

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: AppColors.surface,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      child: SizedBox(
        width: 360,
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.hourglass_bottom, size: 48, color: AppColors.accent),
              const SizedBox(height: 8),
              const Text(
                'Session Timing Out',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(child: _TimeBox(value: '00', label: 'Hours')),
                  const SizedBox(width: 8),
                  Expanded(child: _TimeBox(value: '00', label: 'Minutes')),
                  const SizedBox(width: 8),
                  Expanded(child: _TimeBox(value: _paddedSeconds, label: 'Seconds')),
                ],
              ),
              const SizedBox(height: 12),
              Text(
                'For your security, you will be automatically logged out in $_secondsRemaining seconds due to inactivity.',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: () {
                    _timer?.cancel();
                    widget.onStay();
                  },
                  child: const Text('Stay Logged In'),
                ),
              ),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton(
                  onPressed: () {
                    _timer?.cancel();
                    widget.onLogout();
                  },
                  child: const Text('Logout Now'),
                ),
              ),
            ],
          ),
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
          height: 56,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(8),
            color: AppColors.background,
          ),
          child: Center(
            child: Text(
              value,
              style: TextStyle(
                fontSize: 20,
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
