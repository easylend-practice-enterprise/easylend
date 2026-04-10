import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:kiosk_mode/kiosk_mode.dart' as km;

class KioskService {
  static final KioskService _instance = KioskService._internal();
  factory KioskService() => _instance;
  KioskService._internal();

  bool _isKioskActive = false;
  bool _isManagedKiosk = false;
  bool get isKioskActive => _isKioskActive;
  bool get isManagedKiosk => _isManagedKiosk;

  /// Request kiosk mode and hide the system UI.
  ///
  /// On a managed Android device, this can become a proper lock-task kiosk.
  /// Without device-owner provisioning, Android may fall back to screen pinning.
  Future<void> startKioskMode() async {
    if (_isKioskActive && _isManagedKiosk) return;

    try {
      // Hide system UI bars (status bar, navigation bar)
      await SystemChrome.setEnabledSystemUIMode(
        SystemUiMode.immersiveSticky,
        overlays: [],
      );

      // Start lock-task / screen-pinning kiosk mode
      final didStartKioskMode = await km.startKioskMode();
      final isManagedKiosk = await km.isManagedKiosk();

      _isKioskActive = didStartKioskMode;
      _isManagedKiosk = isManagedKiosk;

      if (!didStartKioskMode) {
        debugPrint('Failed to start kiosk mode.');
      } else if (!isManagedKiosk) {
        debugPrint(
          'Kiosk mode is active but unmanaged. Device owner provisioning is incomplete.',
        );
      }
    } catch (e) {
      debugPrint('Failed to start kiosk mode: $e');
    }
  }

  /// Stop kiosk mode and restore normal system UI.
  Future<void> stopKioskMode() async {
    if (!_isKioskActive) return;

    try {
      final didStopKioskMode = await km.stopKioskMode();

      // Restore system UI
      await SystemChrome.setEnabledSystemUIMode(
        SystemUiMode.manual,
        overlays: SystemUiOverlay.values,
      );

      // Restore orientation
      await SystemChrome.setPreferredOrientations([
        DeviceOrientation.portraitUp,
        DeviceOrientation.landscapeLeft,
        DeviceOrientation.landscapeRight,
        DeviceOrientation.portraitDown,
      ]);

      _isKioskActive = false;
      _isManagedKiosk = false;

      if (didStopKioskMode != true) {
        debugPrint('Failed to stop kiosk mode.');
      }
    } catch (e) {
      debugPrint('Failed to stop kiosk mode: $e');
    }
  }
}
