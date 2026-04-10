import 'dart:async';

import 'package:flutter/material.dart';

import 'kiosk_service.dart';

class KioskModeWrapper extends StatefulWidget {
  const KioskModeWrapper({super.key, required this.child});

  final Widget child;

  @override
  State<KioskModeWrapper> createState() => _KioskModeWrapperState();
}

class _KioskModeWrapperState extends State<KioskModeWrapper>
    with WidgetsBindingObserver {
  final KioskService _kioskService = KioskService();
  bool _activationInProgress = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }

      unawaited(_enableKioskMode());
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(_enableKioskMode());
    }
  }

  Future<void> _enableKioskMode() async {
    if (_activationInProgress) {
      return;
    }

    _activationInProgress = true;

    try {
      await _kioskService.startKioskMode();
    } finally {
      _activationInProgress = false;
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return widget.child;
  }
}
