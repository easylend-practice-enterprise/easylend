import 'package:flutter/material.dart';
import '../theme.dart';

class LendingCompleteScreen extends StatelessWidget {
  const LendingCompleteScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(centerTitle: true, title: const Text('Lending Complete')),
      body: SafeArea(
        child: Column(
          children: [
            const SizedBox(height: 24),
            const Icon(Icons.check_circle, size: 96, color: AppColors.accent),
            const SizedBox(height: 12),
            const Text(
              'Item Lent Successfully',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 24),
              child: Text(
                'Your item has been lent out securely. The grace period has started.',
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
                    _timeBox('00', 'Hours'),
                    const SizedBox(height: 12),
                    _timeBox('04', 'Minutes'),
                    const SizedBox(height: 12),
                    _timeBox('59', 'Seconds'),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(16.0),
              child: OutlinedButton.icon(
                onPressed: () {},
                icon: const Icon(Icons.report_problem),
                label: const Text('Report Pre-existing Damage'),
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size.fromHeight(48),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _timeBox(String value, String label) => Column(
    children: [
      Container(
        height: 64,
        width: double.infinity,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppColors.background),
        ),
        child: Center(
          child: Text(
            value,
            style: const TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
          ),
        ),
      ),
      const SizedBox(height: 6),
      Text(label, style: const TextStyle(fontSize: 12, color: AppColors.text)),
    ],
  );
}
