import 'package:flutter/foundation.dart';

/// Centralized debug mode configuration.
///
/// Set [debugEnabled] to true to enable debug features across the app.
/// This should ALWAYS be false in production/release builds.
class DebugConfig {
  /// Master switch for all debug features.
  /// In release builds, this is always false regardless of this value.
  static const bool debugEnabled = true;

  /// Whether debug mode is truly active (debugEnabled AND running in debug mode)
  static bool get isActive => debugEnabled && kDebugMode;

  /// Test user credentials (non-admin)
  static const String testUsername = 'testuser';
  static const String testPassword = 'testpass123';

  /// Admin credentials for testing admin features
  /// Note: Admin features may not work without backend
  static const String adminUsername = 'admin';
  static const String adminPassword = 'admin123';

  /// Check if credentials are valid
  static bool isValidCredentials(String username, String password) {
    return (username == testUsername && password == testPassword) ||
        (username == adminUsername && password == adminPassword);
  }

  /// Check if credentials are admin
  static bool isAdminCredentials(String username, String password) {
    return username == adminUsername && password == adminPassword;
  }
}

/// Convenience getter for debug mode status
bool get isDebugMode => DebugConfig.isActive;
