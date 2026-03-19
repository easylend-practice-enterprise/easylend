import 'package:flutter/material.dart';
import '../../theme.dart';

class InactivityModal extends StatelessWidget {
  final VoidCallback onStay;
  final VoidCallback onLogout;
  const InactivityModal({
    super.key,
    required this.onStay,
    required this.onLogout,
  });

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Theme.of(context).brightness == Brightness.dark
          ? AppColors.surface
          : AppColors.background,
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
                  Expanded(
                    child: _TimeBox(value: '00', label: 'Hours'),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: _TimeBox(value: '00', label: 'Minutes'),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: _TimeBox(value: '30', label: 'Seconds'),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              const Text(
                'For your security, you will be automatically logged out in 30 seconds due to inactivity.',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: onStay,
                child: const Text('Stay Logged In'),
              ),
              const SizedBox(height: 8),
              OutlinedButton(
                onPressed: onLogout,
                child: const Text('Logout Now'),
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
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
          ),
        ),
        const SizedBox(height: 6),
        Text(label, style: TextStyle(fontSize: 12, color: AppColors.text)),
      ],
    );
  }
}
