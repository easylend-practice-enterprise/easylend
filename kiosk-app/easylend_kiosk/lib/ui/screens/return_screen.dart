import 'package:flutter/material.dart';

import '../../core/app_exceptions.dart';
import '../../services/api/kiosk_api_service.dart';
import '../../theme.dart';
import '../utils/error_dialog.dart';

class ReturnScreen extends StatefulWidget {
  const ReturnScreen({super.key});

  @override
  State<ReturnScreen> createState() => _ReturnScreenState();
}

class _ReturnScreenState extends State<ReturnScreen> {
  final KioskApiService _apiService = KioskApiService();
  final TextEditingController _aztecController = TextEditingController();
  bool _isProcessing = false;

  @override
  void dispose() {
    _aztecController.dispose();
    super.dispose();
  }

  Future<void> _processReturn() async {
    setState(() => _isProcessing = true);

    try {
      await _apiService.initiateReturn(_aztecController.text);
      _aztecController.clear();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Return initiated successfully. Please place the item in the open locker.',
            ),
          ),
        );
      }
    } on AppException catch (e) {
      if (mounted) {
        await showErrorDialog(context, 'Return Failed', e.message);
      }
    } finally {
      if (mounted) {
        setState(() => _isProcessing = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Return Asset'),
        backgroundColor: AppColors.background,
        elevation: 0,
        centerTitle: true,
      ),
      backgroundColor: AppColors.background,
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Text(
                'Scan or enter the asset Aztec Code to return it',
                style: TextStyle(fontSize: 28),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 48),
              TextField(
                controller: _aztecController,
                style: TextStyle(color: AppColors.text, fontSize: 24),
                decoration: InputDecoration(
                  filled: true,
                  fillColor: AppColors.surface,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide.none,
                  ),
                  hintText: 'Aztec Code',
                  hintStyle: TextStyle(color: AppColors.text.withAlpha(128), fontSize: 20),
                ),
              ),
              const SizedBox(height: 36),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: _isProcessing ? null : _processReturn,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.primary,
                    foregroundColor: AppColors.onPrimary,
                    padding: const EdgeInsets.symmetric(vertical: 24),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  child: _isProcessing
                      ? SizedBox(
                          height: 32,
                          width: 32,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: AppColors.onPrimary,
                          ),
                        )
                      : const Text(
                          'Initiate Return',
                          style: TextStyle(fontSize: 22),
                        ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}