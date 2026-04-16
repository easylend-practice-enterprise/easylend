import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../providers/providers.dart';
import '../../theme.dart';

class PinEntryScreen extends ConsumerStatefulWidget {
  final String nfcTagId;

  const PinEntryScreen({super.key, required this.nfcTagId});

  @override
  ConsumerState<PinEntryScreen> createState() => _PinEntryScreenState();
}

class _PinEntryScreenState extends ConsumerState<PinEntryScreen> {
  String _pin = '';
  bool _isLoading = false;
  String? _error;

  void _onDigitPressed(String digit) {
    if (_pin.length < 6) {
      setState(() {
        _pin += digit;
        _error = null;
      });
    }
  }

  void _onBackspacePressed() {
    if (_pin.isNotEmpty) {
      setState(() {
        _pin = _pin.substring(0, _pin.length - 1);
        _error = null;
      });
    }
  }

  void _onClearPressed() {
    setState(() {
      _pin = '';
      _error = null;
    });
  }

  Future<void> _onSubmit() async {
    if (_pin.length != 6) {
      setState(() => _error = 'Please enter a 6-digit PIN');
      return;
    }

    setState(() {
      _isLoading = true;
      _error = null;
    });

    final success = await ref
        .read(authProvider.notifier)
        .pinLogin(widget.nfcTagId, _pin);

    if (!mounted) return;

    setState(() => _isLoading = false);

    if (success) {
      context.go('/catalog');
    } else {
      final authState = ref.read(authProvider);
      setState(() => _error = authState.error ?? 'Login failed');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go('/login'),
        ),
        title: const Text('Enter PIN'),
        centerTitle: true,
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            children: [
              const Spacer(),
              // PIN display
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(6, (index) {
                  final filled = index < _pin.length;
                  return Container(
                    margin: const EdgeInsets.symmetric(horizontal: 8),
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      color: filled ? AppColors.primary : AppColors.surface,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: filled ? AppColors.primary : AppColors.divider,
                        width: 2,
                      ),
                    ),
                    child: Center(
                      child: filled
                          ? Container(
                              width: 16,
                              height: 16,
                              decoration: const BoxDecoration(
                                color: Colors.white,
                                shape: BoxShape.circle,
                              ),
                            )
                          : null,
                    ),
                  );
                }),
              ),
              const SizedBox(height: 16),

              // Error message
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 16),
                  child: Text(
                    _error!,
                    style: const TextStyle(color: Colors.red),
                    textAlign: TextAlign.center,
                  ),
                ),

              const Spacer(),

              // Numeric keypad
              _buildKeypad(),

              const SizedBox(height: 24),

              // Submit button
              SizedBox(
                width: double.infinity,
                height: 56,
                child: ElevatedButton(
                  onPressed: _isLoading || _pin.length != 6 ? null : _onSubmit,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.primary,
                    foregroundColor: Colors.white,
                  ),
                  child: _isLoading
                      ? const SizedBox(
                          width: 24,
                          height: 24,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Text(
                          'LOGIN',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                ),
              ),

              const SizedBox(height: 16),

              // Help text
              TextButton(
                onPressed: () {
                  // Help dialog pending implementation
                },
                child: const Text('Need help?'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildKeypad() {
    return Column(
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: ['1', '2', '3'].map(_buildKey).toList(),
        ),
        const SizedBox(height: 12),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: ['4', '5', '6'].map(_buildKey).toList(),
        ),
        const SizedBox(height: 12),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: ['7', '8', '9'].map(_buildKey).toList(),
        ),
        const SizedBox(height: 12),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: [
            _buildActionKey(Icons.clear, _onClearPressed),
            _buildKey('0'),
            _buildActionKey(Icons.backspace, _onBackspacePressed),
          ],
        ),
      ],
    );
  }

  Widget _buildKey(String digit) {
    return SizedBox(
      width: 80,
      height: 80,
      child: TextButton(
        onPressed: () => _onDigitPressed(digit),
        style: TextButton.styleFrom(
          backgroundColor: AppColors.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(40),
          ),
        ),
        child: Text(
          digit,
          style: const TextStyle(
            fontSize: 32,
            fontWeight: FontWeight.bold,
            color: Colors.white,
          ),
        ),
      ),
    );
  }

  Widget _buildActionKey(IconData icon, VoidCallback onPressed) {
    return SizedBox(
      width: 80,
      height: 80,
      child: TextButton(
        onPressed: onPressed,
        style: TextButton.styleFrom(
          backgroundColor: AppColors.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(40),
          ),
        ),
        child: Icon(icon, color: Colors.white, size: 28),
      ),
    );
  }
}
